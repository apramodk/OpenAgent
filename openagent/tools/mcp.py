"""MCP (Model Context Protocol) host implementation.

MCP allows the agent to call external tool servers via JSON-RPC over stdio.
This module implements the host (client) side of MCP.
"""

import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MCPTool:
    """A tool provided by an MCP server."""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    server_name: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server": self.server_name,
        }


@dataclass
class MCPToolResult:
    """Result from calling an MCP tool."""

    success: bool
    content: Any = None
    error: str | None = None
    is_error: bool = False

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
        }


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    command: list[str]  # Command to start the server
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None


class MCPServer:
    """Connection to a single MCP server."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.name = config.name
        self.process: subprocess.Popen | None = None
        self.tools: dict[str, MCPTool] = {}
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the MCP server process."""
        env = {**dict(subprocess.os.environ), **self.config.env}

        self.process = subprocess.Popen(
            self.config.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self.config.cwd,
            env=env,
        )

        # Start reader task
        self._reader_task = asyncio.create_task(self._read_responses())

        # Initialize and discover tools
        await self._initialize()

    async def stop(self) -> None:
        """Stop the MCP server process."""
        if self._reader_task:
            self._reader_task.cancel()

        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    async def _initialize(self) -> None:
        """Initialize MCP connection and discover tools."""
        # Send initialize request
        result = await self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "openagent",
                "version": "0.1.0",
            },
        })

        # Send initialized notification
        self._notify("notifications/initialized", {})

        # Discover tools
        await self._discover_tools()

    async def _discover_tools(self) -> None:
        """Discover available tools from the server."""
        result = await self._request("tools/list", {})

        self.tools = {}
        for tool_data in result.get("tools", []):
            tool = MCPTool(
                name=tool_data["name"],
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
                server_name=self.name,
            )
            self.tools[tool.name] = tool

    async def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """Call a tool on this server."""
        if name not in self.tools:
            return MCPToolResult(
                success=False,
                error=f"Unknown tool: {name}",
                is_error=True,
            )

        try:
            result = await self._request("tools/call", {
                "name": name,
                "arguments": arguments,
            })

            # Parse MCP tool result format
            content = result.get("content", [])
            is_error = result.get("isError", False)

            # Extract text content
            text_content = []
            for item in content:
                if item.get("type") == "text":
                    text_content.append(item.get("text", ""))

            return MCPToolResult(
                success=not is_error,
                content="\n".join(text_content) if text_content else content,
                is_error=is_error,
            )

        except Exception as e:
            return MCPToolResult(
                success=False,
                error=str(e),
                is_error=True,
            )

    async def _request(self, method: str, params: dict) -> dict:
        """Send a request and wait for response."""
        self._request_id += 1
        request_id = self._request_id

        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        # Create future for response
        future: asyncio.Future = asyncio.Future()
        self._pending[request_id] = future

        # Send request
        self._write(request)

        # Wait for response
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        finally:
            self._pending.pop(request_id, None)

    def _notify(self, method: str, params: dict) -> None:
        """Send a notification (no response expected)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        self._write(notification)

    def _write(self, data: dict) -> None:
        """Write JSON-RPC message to server stdin."""
        if self.process and self.process.stdin:
            message = json.dumps(data) + "\n"
            self.process.stdin.write(message.encode())
            self.process.stdin.flush()

    async def _read_responses(self) -> None:
        """Read responses from server stdout."""
        if not self.process or not self.process.stdout:
            return

        loop = asyncio.get_event_loop()

        while True:
            try:
                # Read line in executor to avoid blocking
                line = await loop.run_in_executor(
                    None,
                    self.process.stdout.readline,
                )

                if not line:
                    break

                data = json.loads(line.decode())

                # Handle response
                if "id" in data and data["id"] in self._pending:
                    future = self._pending[data["id"]]
                    if "error" in data:
                        future.set_exception(
                            Exception(data["error"].get("message", "Unknown error"))
                        )
                    else:
                        future.set_result(data.get("result", {}))

            except asyncio.CancelledError:
                break
            except Exception:
                continue


class MCPHost:
    """
    MCP host that manages multiple MCP servers.

    The host is responsible for:
    - Starting/stopping MCP servers
    - Routing tool calls to the correct server
    - Aggregating tools from all servers
    """

    def __init__(self):
        self._servers: dict[str, MCPServer] = {}
        self._tools: dict[str, MCPTool] = {}

    async def add_server(self, config: MCPServerConfig) -> None:
        """Add and start an MCP server."""
        server = MCPServer(config)
        await server.start()

        self._servers[config.name] = server

        # Register tools from this server
        for tool in server.tools.values():
            self._tools[tool.name] = tool

    async def remove_server(self, name: str) -> None:
        """Stop and remove an MCP server."""
        if name in self._servers:
            server = self._servers[name]
            await server.stop()

            # Remove tools from this server
            self._tools = {
                k: v for k, v in self._tools.items()
                if v.server_name != name
            }

            del self._servers[name]

    async def shutdown(self) -> None:
        """Shutdown all MCP servers."""
        for server in list(self._servers.values()):
            await server.stop()
        self._servers.clear()
        self._tools.clear()

    def list_tools(self) -> list[MCPTool]:
        """List all available tools from all servers."""
        return list(self._tools.values())

    def get_tool(self, name: str) -> MCPTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    async def call_tool(self, name: str, arguments: dict) -> MCPToolResult:
        """Call a tool by name."""
        tool = self._tools.get(name)
        if not tool:
            return MCPToolResult(
                success=False,
                error=f"Unknown tool: {name}",
                is_error=True,
            )

        server = self._servers.get(tool.server_name)
        if not server:
            return MCPToolResult(
                success=False,
                error=f"Server not found: {tool.server_name}",
                is_error=True,
            )

        return await server.call_tool(name, arguments)

    def to_llm_format(self) -> list[dict]:
        """Convert tools to LLM function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in self._tools.values()
        ]
