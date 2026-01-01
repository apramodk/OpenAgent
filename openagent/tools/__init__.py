"""Tool execution and MCP integration."""

from openagent.tools.registry import Tool, ToolRegistry
from openagent.tools.executor import ToolExecutor, ToolCall, ToolResult
from openagent.tools.mcp import MCPHost, MCPServer, MCPServerConfig, MCPTool, MCPToolResult
from openagent.tools.builtin import register_builtin_tools

__all__ = [
    # Registry
    "Tool",
    "ToolRegistry",
    # Executor
    "ToolExecutor",
    "ToolCall",
    "ToolResult",
    # MCP
    "MCPHost",
    "MCPServer",
    "MCPServerConfig",
    "MCPTool",
    "MCPToolResult",
    # Built-in
    "register_builtin_tools",
]
