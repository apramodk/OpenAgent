"""Agent with tool execution capabilities."""

import json
from dataclasses import dataclass
from typing import AsyncIterator

from openagent.core.agent import Agent, AgentConfig
from openagent.core.llm import LLMClient
from openagent.tools.registry import ToolRegistry
from openagent.tools.executor import ToolExecutor, ToolCall, ToolResult
from openagent.tools.builtin import register_builtin_tools


@dataclass
class ToolAgentConfig(AgentConfig):
    """Configuration for ToolAgent."""

    max_tool_iterations: int = 10
    enable_filesystem: bool = True
    enable_shell: bool = False  # Disabled by default for safety
    enable_git: bool = True


class ToolAgent(Agent):
    """
    Agent that can use tools during conversation.

    Extends base Agent with tool calling capabilities.
    The agent will automatically decide when to use tools
    based on the user's request.
    """

    def __init__(
        self,
        config: ToolAgentConfig | None = None,
        registry: ToolRegistry | None = None,
        **kwargs,
    ):
        self.tool_config = config or ToolAgentConfig()
        super().__init__(config=self.tool_config, **kwargs)

        # Set up tool registry
        self.registry = registry or ToolRegistry()
        self.executor = ToolExecutor(self.registry, max_iterations=self.tool_config.max_tool_iterations)

        # Register built-in tools based on config
        categories = []
        if self.tool_config.enable_filesystem:
            categories.append("filesystem")
        if self.tool_config.enable_shell:
            categories.append("shell")
        if self.tool_config.enable_git:
            categories.append("git")

        if categories:
            register_builtin_tools(self.registry, categories)

    def _get_tool_prompt(self) -> str:
        """Generate tool usage instructions for the system prompt."""
        tools = self.registry.list_all()
        if not tools:
            return ""

        tool_descriptions = []
        for tool in tools:
            params = tool.input_schema.get("properties", {})
            param_str = ", ".join(
                f"{k}: {v.get('type', 'any')}"
                for k, v in params.items()
            )
            tool_descriptions.append(
                f"- {tool.name}({param_str}): {tool.description}"
            )

        return f"""
You have access to the following tools:

{chr(10).join(tool_descriptions)}

To use a tool, respond with a JSON object in this exact format:
{{"tool": "tool_name", "args": {{"param1": "value1"}}}}

Only use tools when necessary to answer the user's question.
After receiving tool results, provide a natural language response.
"""

    def _parse_tool_call(self, response: str) -> ToolCall | None:
        """Try to parse a tool call from the response."""
        try:
            # Try to find JSON in the response
            response = response.strip()

            # Look for JSON object
            start = response.find("{")
            end = response.rfind("}") + 1

            if start == -1 or end == 0:
                return None

            json_str = response[start:end]
            data = json.loads(json_str)

            if "tool" in data:
                return ToolCall(
                    name=data["tool"],
                    params=data.get("args", {}),
                    reasoning=data.get("reasoning", ""),
                )
        except (json.JSONDecodeError, KeyError):
            pass

        return None

    async def chat_with_tools(
        self,
        message: str,
        rag_context: str | None = None,
    ) -> str:
        """
        Process message with automatic tool execution.

        The agent will:
        1. Analyze the request
        2. Decide if tools are needed
        3. Execute tools if needed
        4. Incorporate results into response
        """
        # Add tool instructions to context
        tool_prompt = self._get_tool_prompt()
        original_system = self.config.system_prompt
        if tool_prompt:
            self.config.system_prompt = f"{original_system}\n{tool_prompt}"

        iterations = 0
        tool_results: list[tuple[ToolCall, ToolResult]] = []

        try:
            while iterations < self.tool_config.max_tool_iterations:
                iterations += 1

                # Build context with tool results
                context_message = message
                if tool_results:
                    results_str = "\n".join(
                        f"Tool {call.name} returned: {json.dumps(result.output)}"
                        for call, result in tool_results
                    )
                    context_message = f"{message}\n\nPrevious tool results:\n{results_str}\n\nNow provide your response:"

                # Get response
                response = await self.chat(context_message, rag_context=rag_context)

                # Check if response contains a tool call
                tool_call = self._parse_tool_call(response)

                if tool_call is None:
                    # No tool call, return the response
                    return response

                # Execute the tool
                result = await self.executor.execute(tool_call)
                tool_results.append((tool_call, result))

                # If tool failed, include error in next iteration
                if not result.success:
                    # Add error context for next iteration
                    message = f"{message}\n\nNote: Tool {tool_call.name} failed with: {result.error}"

            # Max iterations reached
            return "I've used the maximum number of tool calls. Here's what I found:\n" + \
                   "\n".join(f"- {call.name}: {result.output}" for call, result in tool_results)

        finally:
            # Restore original system prompt
            self.config.system_prompt = original_system

    async def chat_stream_with_tools(
        self,
        message: str,
        rag_context: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream response with tool execution.

        Yields status updates during tool execution and
        streams the final response.
        """
        tool_prompt = self._get_tool_prompt()
        original_system = self.config.system_prompt
        if tool_prompt:
            self.config.system_prompt = f"{original_system}\n{tool_prompt}"

        iterations = 0
        tool_results: list[tuple[ToolCall, ToolResult]] = []

        try:
            while iterations < self.tool_config.max_tool_iterations:
                iterations += 1

                context_message = message
                if tool_results:
                    results_str = "\n".join(
                        f"Tool {call.name} returned: {json.dumps(result.output)}"
                        for call, result in tool_results
                    )
                    context_message = f"{message}\n\nPrevious tool results:\n{results_str}"

                # Collect full response first to check for tool calls
                full_response = ""
                async for chunk in self.chat_stream(context_message, rag_context=rag_context):
                    full_response += chunk

                # Check for tool call
                tool_call = self._parse_tool_call(full_response)

                if tool_call is None:
                    # Stream the final response
                    for char in full_response:
                        yield char
                    return

                # Notify about tool execution
                yield f"\n🔧 Using tool: {tool_call.name}...\n"

                # Execute tool
                result = await self.executor.execute(tool_call)
                tool_results.append((tool_call, result))

                if result.success:
                    yield f"✓ Got result from {tool_call.name}\n"
                else:
                    yield f"✗ Tool error: {result.error}\n"

        finally:
            self.config.system_prompt = original_system

    def list_tools(self) -> list[dict]:
        """List available tools."""
        return [tool.to_dict() for tool in self.registry.list_all()]
