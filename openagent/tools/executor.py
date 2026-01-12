"""Tool execution loop."""

from dataclasses import dataclass, field
from typing import Any
import json

from openagent.tools.registry import Tool, ToolRegistry


@dataclass
class ToolCall:
    """A request to call a tool."""

    name: str
    params: dict = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class ToolResult:
    """Result from a tool execution."""

    success: bool
    output: Any = None
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


class ToolExecutor:
    """Executes tools from the registry."""

    def __init__(
        self,
        registry: ToolRegistry,
        max_iterations: int = 10,
    ):
        self.registry = registry
        self.max_iterations = max_iterations

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a single tool call."""
        tool = self.registry.get(call.name)

        if not tool:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {call.name}",
            )

        if not tool.handler:
            return ToolResult(
                success=False,
                error=f"Tool {call.name} has no handler (may be MCP-only)",
            )

        try:
            result = await tool.handler(**call.params)
            return ToolResult(success=True, output=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def execute_batch(
        self,
        calls: list[ToolCall],
    ) -> list[ToolResult]:
        """Execute multiple tool calls sequentially."""
        results = []
        for call in calls:
            result = await self.execute(call)
            results.append(result)
        return results

    def validate_call(self, call: ToolCall) -> tuple[bool, str]:
        """
        Validate a tool call before execution.

        Returns (is_valid, error_message).
        """
        tool = self.registry.get(call.name)

        if not tool:
            return False, f"Unknown tool: {call.name}"

        # Validate required parameters
        schema = tool.input_schema
        required = schema.get("required", [])

        for param in required:
            if param not in call.params:
                return False, f"Missing required parameter: {param}"

        return True, ""
