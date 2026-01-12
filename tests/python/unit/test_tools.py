"""Tests for tool registry and executor."""

import pytest

from openagent.tools.registry import Tool, ToolRegistry
from openagent.tools.executor import ToolExecutor, ToolCall, ToolResult


class TestTool:
    """Tests for Tool dataclass."""

    def test_to_dict(self):
        """Test dictionary conversion."""
        tool = Tool(
            name="search",
            description="Search the codebase",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            server="codebase",
        )

        d = tool.to_dict()

        assert d["name"] == "search"
        assert d["description"] == "Search the codebase"
        assert d["input_schema"]["type"] == "object"
        assert d["server"] == "codebase"


class TestToolRegistry:
    """Tests for ToolRegistry class."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        """Create an empty registry."""
        return ToolRegistry()

    def test_register_tool(self, registry: ToolRegistry):
        """Test registering a tool."""
        tool = Tool(name="test", description="Test tool")
        registry.register(tool)

        assert registry.get("test") is not None
        assert registry.get("test").name == "test"

    def test_register_function(self, registry: ToolRegistry):
        """Test registering a function as a tool."""
        async def my_handler(query: str) -> str:
            return f"Result for: {query}"

        tool = registry.register_function(
            name="search",
            description="Search function",
            handler=my_handler,
            input_schema={"type": "object"},
        )

        assert tool.name == "search"
        assert tool.handler is my_handler
        assert registry.get("search") is not None

    def test_get_nonexistent(self, registry: ToolRegistry):
        """Test getting nonexistent tool."""
        assert registry.get("nonexistent") is None

    def test_list_all(self, registry: ToolRegistry):
        """Test listing all tools."""
        registry.register(Tool(name="tool1", description="Tool 1"))
        registry.register(Tool(name="tool2", description="Tool 2"))

        tools = registry.list_all()

        assert len(tools) == 2
        names = [t.name for t in tools]
        assert "tool1" in names
        assert "tool2" in names

    def test_list_names(self, registry: ToolRegistry):
        """Test listing tool names."""
        registry.register(Tool(name="tool1", description="Tool 1"))
        registry.register(Tool(name="tool2", description="Tool 2"))

        names = registry.list_names()

        assert names == ["tool1", "tool2"]

    def test_unregister(self, registry: ToolRegistry):
        """Test unregistering a tool."""
        registry.register(Tool(name="test", description="Test"))

        result = registry.unregister("test")

        assert result is True
        assert registry.get("test") is None

    def test_unregister_nonexistent(self, registry: ToolRegistry):
        """Test unregistering nonexistent tool."""
        result = registry.unregister("nonexistent")
        assert result is False

    def test_clear(self, registry: ToolRegistry):
        """Test clearing all tools."""
        registry.register(Tool(name="tool1", description="Tool 1"))
        registry.register(Tool(name="tool2", description="Tool 2"))

        registry.clear()

        assert len(registry.list_all()) == 0

    def test_to_llm_format(self, registry: ToolRegistry):
        """Test conversion to LLM function-calling format."""
        registry.register(
            Tool(
                name="search",
                description="Search the codebase",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            )
        )

        llm_format = registry.to_llm_format()

        assert len(llm_format) == 1
        assert llm_format[0]["type"] == "function"
        assert llm_format[0]["function"]["name"] == "search"
        assert llm_format[0]["function"]["description"] == "Search the codebase"


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_success_result(self):
        """Test successful result."""
        result = ToolResult(success=True, output={"data": "value"})

        assert result.success is True
        assert result.output == {"data": "value"}
        assert result.error is None

    def test_error_result(self):
        """Test error result."""
        result = ToolResult(success=False, error="Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"

    def test_to_dict(self):
        """Test dictionary conversion."""
        result = ToolResult(success=True, output="data")
        d = result.to_dict()

        assert d == {"success": True, "output": "data", "error": None}

    def test_to_json(self):
        """Test JSON conversion."""
        result = ToolResult(success=True, output="data")
        j = result.to_json()

        assert '"success": true' in j
        assert '"output": "data"' in j


class TestToolExecutor:
    """Tests for ToolExecutor class."""

    @pytest.fixture
    def executor(self) -> ToolExecutor:
        """Create an executor with test tools."""
        registry = ToolRegistry()

        async def echo_handler(message: str) -> str:
            return f"Echo: {message}"

        async def error_handler() -> None:
            raise ValueError("Test error")

        registry.register_function(
            name="echo",
            description="Echo a message",
            handler=echo_handler,
            input_schema={
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        )

        registry.register_function(
            name="error",
            description="Always errors",
            handler=error_handler,
        )

        registry.register(
            Tool(name="no_handler", description="No handler", handler=None)
        )

        return ToolExecutor(registry)

    @pytest.mark.asyncio
    async def test_execute_success(self, executor: ToolExecutor):
        """Test successful tool execution."""
        call = ToolCall(name="echo", params={"message": "Hello"})
        result = await executor.execute(call)

        assert result.success is True
        assert result.output == "Echo: Hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, executor: ToolExecutor):
        """Test executing unknown tool."""
        call = ToolCall(name="unknown", params={})
        result = await executor.execute(call)

        assert result.success is False
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_no_handler(self, executor: ToolExecutor):
        """Test executing tool with no handler."""
        call = ToolCall(name="no_handler", params={})
        result = await executor.execute(call)

        assert result.success is False
        assert "no handler" in result.error

    @pytest.mark.asyncio
    async def test_execute_handler_error(self, executor: ToolExecutor):
        """Test handling errors from tool handler."""
        call = ToolCall(name="error", params={})
        result = await executor.execute(call)

        assert result.success is False
        assert "Test error" in result.error

    @pytest.mark.asyncio
    async def test_execute_batch(self, executor: ToolExecutor):
        """Test batch execution."""
        calls = [
            ToolCall(name="echo", params={"message": "First"}),
            ToolCall(name="echo", params={"message": "Second"}),
        ]
        results = await executor.execute_batch(calls)

        assert len(results) == 2
        assert results[0].output == "Echo: First"
        assert results[1].output == "Echo: Second"

    def test_validate_call_valid(self, executor: ToolExecutor):
        """Test validating a valid call."""
        call = ToolCall(name="echo", params={"message": "Hello"})
        is_valid, error = executor.validate_call(call)

        assert is_valid is True
        assert error == ""

    def test_validate_call_unknown(self, executor: ToolExecutor):
        """Test validating unknown tool."""
        call = ToolCall(name="unknown", params={})
        is_valid, error = executor.validate_call(call)

        assert is_valid is False
        assert "Unknown tool" in error

    def test_validate_call_missing_param(self, executor: ToolExecutor):
        """Test validating call with missing required param."""
        call = ToolCall(name="echo", params={})
        is_valid, error = executor.validate_call(call)

        assert is_valid is False
        assert "Missing required parameter" in error
