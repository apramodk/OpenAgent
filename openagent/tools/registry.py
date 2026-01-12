"""Tool registration and discovery."""

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class Tool:
    """A callable tool."""

    name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    handler: Callable[..., Awaitable[Any]] | None = None
    server: str = ""  # MCP server name, if external

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server": self.server,
        }


class ToolRegistry:
    """Registry for available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def register_function(
        self,
        name: str,
        description: str,
        handler: Callable[..., Awaitable[Any]],
        input_schema: dict | None = None,
    ) -> Tool:
        """Register a function as a tool."""
        tool = Tool(
            name=name,
            description=description,
            input_schema=input_schema or {},
            handler=handler,
        )
        self.register(tool)
        return tool

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """List all tool names."""
        return list(self._tools.keys())

    def unregister(self, name: str) -> bool:
        """Unregister a tool."""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def clear(self) -> None:
        """Clear all registered tools."""
        self._tools.clear()

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
