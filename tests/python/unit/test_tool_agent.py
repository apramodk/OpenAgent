"""Tests for ToolAgent."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openagent.core.tool_agent import ToolAgent, ToolAgentConfig
from openagent.tools.registry import ToolRegistry, Tool
from openagent.tools.executor import ToolCall, ToolResult


class TestToolAgentConfig:
    """Tests for ToolAgentConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ToolAgentConfig()
        assert config.max_tool_iterations == 10
        assert config.enable_filesystem is True
        assert config.enable_shell is False  # Disabled by default for safety
        assert config.enable_git is True

    def test_custom_config(self):
        """Test custom configuration."""
        config = ToolAgentConfig(
            max_tool_iterations=5,
            enable_filesystem=False,
            enable_shell=True,
            enable_git=False,
        )
        assert config.max_tool_iterations == 5
        assert config.enable_filesystem is False
        assert config.enable_shell is True
        assert config.enable_git is False

    def test_inherits_agent_config(self):
        """Test that ToolAgentConfig inherits from AgentConfig."""
        config = ToolAgentConfig(
            system_prompt="Custom prompt",
            max_tokens=2048,
        )
        assert config.system_prompt == "Custom prompt"
        assert config.max_tokens == 2048


class TestToolAgentInit:
    """Tests for ToolAgent initialization."""

    @patch("openagent.core.tool_agent.register_builtin_tools")
    def test_default_init(self, mock_register):
        """Test default initialization."""
        agent = ToolAgent()

        assert agent.tool_config is not None
        assert agent.registry is not None
        assert agent.executor is not None

        # Should register filesystem and git by default
        mock_register.assert_called_once()
        call_args = mock_register.call_args
        assert "filesystem" in call_args[0][1]
        assert "git" in call_args[0][1]
        assert "shell" not in call_args[0][1]

    @patch("openagent.core.tool_agent.register_builtin_tools")
    def test_custom_registry(self, mock_register):
        """Test with custom registry."""
        registry = ToolRegistry()
        agent = ToolAgent(registry=registry)

        assert agent.registry is registry

    @patch("openagent.core.tool_agent.register_builtin_tools")
    def test_no_tools_when_all_disabled(self, mock_register):
        """Test no tools registered when all disabled."""
        config = ToolAgentConfig(
            enable_filesystem=False,
            enable_shell=False,
            enable_git=False,
        )
        agent = ToolAgent(config=config)

        # Should not call register_builtin_tools when no categories
        mock_register.assert_not_called()


class TestToolPromptGeneration:
    """Tests for tool prompt generation."""

    def test_empty_registry(self):
        """Test prompt with no tools."""
        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=False,
                enable_git=False,
            )
        )
        prompt = agent._get_tool_prompt()
        assert prompt == ""

    def test_with_tools(self):
        """Test prompt generation with tools."""
        registry = ToolRegistry()
        registry.register(Tool(
            name="test_tool",
            description="A test tool",
            input_schema={
                "type": "object",
                "properties": {
                    "arg1": {"type": "string"},
                    "arg2": {"type": "integer"},
                },
            },
        ))

        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=False,
                enable_git=False,
            ),
            registry=registry,
        )

        prompt = agent._get_tool_prompt()

        assert "test_tool" in prompt
        assert "A test tool" in prompt
        assert "arg1: string" in prompt
        assert "arg2: integer" in prompt
        assert '{"tool": "tool_name"' in prompt


class TestToolCallParsing:
    """Tests for parsing tool calls from responses."""

    def setup_method(self):
        """Set up test agent."""
        self.agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=False,
                enable_git=False,
            )
        )

    def test_parse_valid_tool_call(self):
        """Test parsing a valid tool call."""
        response = '{"tool": "read_file", "args": {"path": "/test.txt"}}'
        call = self.agent._parse_tool_call(response)

        assert call is not None
        assert call.name == "read_file"
        assert call.params == {"path": "/test.txt"}

    def test_parse_tool_call_with_reasoning(self):
        """Test parsing tool call with reasoning."""
        response = '{"tool": "search", "args": {"query": "test"}, "reasoning": "Need to find test files"}'
        call = self.agent._parse_tool_call(response)

        assert call is not None
        assert call.name == "search"
        assert call.reasoning == "Need to find test files"

    def test_parse_tool_call_embedded_in_text(self):
        """Test parsing tool call embedded in natural language."""
        response = 'Let me check that file for you. {"tool": "read_file", "args": {"path": "/test.txt"}} I will analyze it.'
        call = self.agent._parse_tool_call(response)

        assert call is not None
        assert call.name == "read_file"

    def test_parse_no_tool_call(self):
        """Test parsing response with no tool call."""
        response = "Here is my answer to your question."
        call = self.agent._parse_tool_call(response)

        assert call is None

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        response = '{"tool": "broken'
        call = self.agent._parse_tool_call(response)

        assert call is None

    def test_parse_json_without_tool_key(self):
        """Test parsing JSON without tool key."""
        response = '{"name": "something", "value": 123}'
        call = self.agent._parse_tool_call(response)

        assert call is None

    def test_parse_empty_args(self):
        """Test parsing tool call with no args."""
        response = '{"tool": "list_files"}'
        call = self.agent._parse_tool_call(response)

        assert call is not None
        assert call.name == "list_files"
        assert call.params == {}


class TestChatWithTools:
    """Tests for chat_with_tools method."""

    @pytest.fixture
    def mock_agent(self):
        """Create agent with mocked dependencies."""
        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=False,
                enable_git=False,
            )
        )
        return agent

    @pytest.mark.asyncio
    async def test_no_tool_call(self, mock_agent):
        """Test response without tool usage."""
        mock_agent.chat = AsyncMock(return_value="Here is my answer.")

        result = await mock_agent.chat_with_tools("What is 2+2?")

        assert result == "Here is my answer."
        mock_agent.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_tool_call(self, mock_agent):
        """Test single tool execution."""
        # First call returns tool use, second returns final answer
        mock_agent.chat = AsyncMock(side_effect=[
            '{"tool": "read_file", "args": {"path": "/test.txt"}}',
            "The file contains: test content",
        ])
        mock_agent.executor.execute = AsyncMock(return_value=ToolResult(
            output="test content",
            success=True,
        ))

        result = await mock_agent.chat_with_tools("Read the test file")

        assert "test content" in result
        assert mock_agent.executor.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_tool_error_handling(self, mock_agent):
        """Test handling of tool execution errors."""
        mock_agent.chat = AsyncMock(side_effect=[
            '{"tool": "read_file", "args": {"path": "/nonexistent.txt"}}',
            "I could not read the file because it doesn't exist.",
        ])
        mock_agent.executor.execute = AsyncMock(return_value=ToolResult(
            output=None,
            error="File not found",
            success=False,
        ))

        result = await mock_agent.chat_with_tools("Read a nonexistent file")

        assert "could not" in result.lower() or "exist" in result.lower()

    @pytest.mark.asyncio
    async def test_max_iterations(self, mock_agent):
        """Test max iterations limit."""
        mock_agent.tool_config.max_tool_iterations = 2

        # Always return tool call to hit limit
        mock_agent.chat = AsyncMock(return_value='{"tool": "test", "args": {}}')
        mock_agent.executor.execute = AsyncMock(return_value=ToolResult(
            output="result",
            success=True,
        ))

        result = await mock_agent.chat_with_tools("Keep using tools")

        assert "maximum" in result.lower()
        assert mock_agent.executor.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_system_prompt_restored(self, mock_agent):
        """Test that system prompt is restored after tool execution."""
        original_prompt = mock_agent.config.system_prompt
        mock_agent.chat = AsyncMock(return_value="Done")

        await mock_agent.chat_with_tools("Test")

        assert mock_agent.config.system_prompt == original_prompt

    @pytest.mark.asyncio
    async def test_system_prompt_restored_on_error(self, mock_agent):
        """Test system prompt restoration even on error."""
        original_prompt = mock_agent.config.system_prompt
        mock_agent.chat = AsyncMock(side_effect=Exception("Test error"))

        with pytest.raises(Exception):
            await mock_agent.chat_with_tools("Test")

        assert mock_agent.config.system_prompt == original_prompt


class TestListTools:
    """Tests for list_tools method."""

    def test_list_empty(self):
        """Test listing with no tools."""
        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=False,
                enable_git=False,
            )
        )
        tools = agent.list_tools()
        assert tools == []

    def test_list_with_tools(self):
        """Test listing registered tools."""
        registry = ToolRegistry()
        registry.register(Tool(
            name="tool1",
            description="First tool",
            input_schema={"type": "object"},
        ))
        registry.register(Tool(
            name="tool2",
            description="Second tool",
            input_schema={"type": "object"},
        ))

        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=False,
                enable_git=False,
            ),
            registry=registry,
        )

        tools = agent.list_tools()

        assert len(tools) == 2
        names = [t["name"] for t in tools]
        assert "tool1" in names
        assert "tool2" in names


class TestIntegrationWithBuiltinTools:
    """Integration tests with built-in tools."""

    def test_filesystem_tools_registered(self):
        """Test that filesystem tools are registered by default."""
        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=True,
                enable_shell=False,
                enable_git=False,
            )
        )

        tools = agent.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "list_directory" in tool_names

    def test_git_tools_registered(self):
        """Test that git tools are registered when enabled."""
        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=False,
                enable_git=True,
            )
        )

        tools = agent.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "git_status" in tool_names
        assert "git_diff" in tool_names

    def test_shell_tools_when_enabled(self):
        """Test that shell tools are registered when explicitly enabled."""
        agent = ToolAgent(
            config=ToolAgentConfig(
                enable_filesystem=False,
                enable_shell=True,
                enable_git=False,
            )
        )

        tools = agent.list_tools()
        tool_names = [t["name"] for t in tools]

        assert "run_command" in tool_names
