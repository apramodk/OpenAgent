"""Tests for context window management.

## Test Classification

| Category | Tests | Description |
|----------|-------|-------------|
| Configuration | 3 | Config defaults, token budgets |
| Context Building | 6 | Message selection, ordering |
| Token Budget | 4 | Budget constraints, truncation |
| RAG Integration | 2 | RAG context injection |
| Summarization | 3 | Summary triggers, caching |
"""

import pytest
from pathlib import Path

from openagent.memory.context import (
    ContextManager,
    ContextConfig,
    ContextWindow,
    SummarizationRequest,
)
from openagent.memory.session import SessionManager
from openagent.memory.conversation import ConversationHistory


class TestContextConfig:
    """Tests for ContextConfig dataclass."""

    def test_defaults(self):
        """Test default configuration values."""
        config = ContextConfig()

        assert config.max_tokens == 8000
        assert config.reserved_for_response == 1000
        assert config.recent_messages == 20
        assert config.max_rag_tokens == 2000

    def test_available_for_context(self):
        """Test available token calculation."""
        config = ContextConfig(max_tokens=10000, reserved_for_response=2000)

        assert config.available_for_context == 8000

    def test_custom_config(self):
        """Test custom configuration."""
        config = ContextConfig(
            max_tokens=4000,
            recent_messages=10,
            summarize_after=20,
        )

        assert config.max_tokens == 4000
        assert config.recent_messages == 10
        assert config.summarize_after == 20


class TestContextWindow:
    """Tests for ContextWindow dataclass."""

    def test_to_llm_format(self):
        """Test LLM format conversion."""
        window = ContextWindow(
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hello"},
            ],
            total_tokens=20,
            included_message_count=2,
        )

        assert window.to_llm_format() == window.messages

    def test_empty_window(self):
        """Test empty context window."""
        window = ContextWindow()

        assert window.messages == []
        assert window.total_tokens == 0
        assert window.truncated is False


class TestContextManager:
    """Tests for ContextManager class."""

    @pytest.fixture
    def manager(self) -> ContextManager:
        """Create a context manager with default config."""
        return ContextManager()

    @pytest.fixture
    def history(self, tmp_db_path: Path) -> ConversationHistory:
        """Create a conversation history with test data."""
        session_mgr = SessionManager(tmp_db_path)
        session = session_mgr.create(name="Test")
        history = ConversationHistory(session, tmp_db_path)

        # Add some messages
        history.add("user", "Hello!", token_count=5)
        history.add("assistant", "Hi there! How can I help?", token_count=15)
        history.add("user", "Tell me about Python.", token_count=10)
        history.add("assistant", "Python is a programming language...", token_count=50)

        return history

    def test_build_basic(self, manager: ContextManager, history: ConversationHistory):
        """Test basic context building."""
        window = manager.build(
            history=history,
            user_message="What else?",
        )

        assert len(window.messages) > 0
        assert window.messages[-1]["role"] == "user"
        assert window.messages[-1]["content"] == "What else?"

    def test_build_with_system_prompt(self, manager: ContextManager, history: ConversationHistory):
        """Test context building with system prompt."""
        window = manager.build(
            history=history,
            user_message="Hello",
            system_prompt="You are a helpful assistant.",
        )

        assert window.messages[0]["role"] == "system"
        assert "helpful assistant" in window.messages[0]["content"]

    def test_build_with_rag_context(self, manager: ContextManager, history: ConversationHistory):
        """Test context building with RAG context."""
        rag_context = "Function: def hello(): pass\nReturns greeting."

        window = manager.build(
            history=history,
            user_message="How does hello work?",
            rag_context=rag_context,
        )

        # RAG context should be in a system message
        system_messages = [m for m in window.messages if m["role"] == "system"]
        assert any("Relevant context" in m["content"] for m in system_messages)
        assert window.rag_chunks_used > 0

    def test_build_includes_recent_messages(self, manager: ContextManager, history: ConversationHistory):
        """Test that recent messages are included."""
        window = manager.build(
            history=history,
            user_message="Continue",
        )

        # Should include the conversation history
        contents = [m["content"] for m in window.messages]
        assert any("Python" in c for c in contents)

    def test_build_respects_token_budget(self, tmp_db_path: Path):
        """Test that token budget is respected."""
        session_mgr = SessionManager(tmp_db_path)
        session = session_mgr.create(name="Test")
        history = ConversationHistory(session, tmp_db_path)

        # Add many large messages
        for i in range(20):
            history.add("user", f"Message {i}: " + "x" * 500, token_count=150)
            history.add("assistant", f"Response {i}: " + "y" * 500, token_count=150)

        # Small token budget
        config = ContextConfig(max_tokens=1000, reserved_for_response=200)
        manager = ContextManager(config)

        window = manager.build(
            history=history,
            user_message="Final message",
        )

        # Should be truncated
        assert window.total_tokens <= config.available_for_context
        assert window.included_message_count < 40  # Not all messages

    def test_build_simple(self, manager: ContextManager):
        """Test simple context building from message list."""
        from openagent.memory.conversation import Message
        from datetime import datetime

        messages = [
            Message(1, "sess", "system", "You are helpful", 10, datetime.now(), {}),
            Message(2, "sess", "user", "Hello", 5, datetime.now(), {}),
            Message(3, "sess", "assistant", "Hi!", 5, datetime.now(), {}),
        ]

        window = manager.build_simple(messages, max_tokens=100)

        assert len(window.messages) == 3
        assert window.truncated is False

    def test_build_simple_truncates(self, manager: ContextManager):
        """Test simple build truncates when over budget."""
        from openagent.memory.conversation import Message
        from datetime import datetime

        messages = [
            Message(i, "sess", "user", "x" * 400, 100, datetime.now(), {})
            for i in range(10)
        ]

        window = manager.build_simple(messages, max_tokens=300)

        assert len(window.messages) < 10
        assert window.truncated is True

    def test_should_summarize_false(self, manager: ContextManager, history: ConversationHistory):
        """Test summarization not triggered for short history."""
        assert manager.should_summarize(history) is False

    def test_should_summarize_true(self, tmp_db_path: Path):
        """Test summarization triggered for long history."""
        session_mgr = SessionManager(tmp_db_path)
        session = session_mgr.create(name="Test")
        history = ConversationHistory(session, tmp_db_path)

        # Add many messages
        for i in range(35):
            history.add("user", f"Message {i}")
            history.add("assistant", f"Response {i}")

        config = ContextConfig(summarize_after=30)
        manager = ContextManager(config)

        assert manager.should_summarize(history) is True

    def test_set_and_get_summary(self, manager: ContextManager):
        """Test summary caching."""
        session_id = "test-session"
        summary = "This conversation discussed Python programming."

        manager.set_summary(session_id, summary)

        # Summary should be cached
        assert manager._summary_cache[session_id] == summary

    def test_invalidate_summary(self, manager: ContextManager):
        """Test summary invalidation."""
        session_id = "test-session"
        manager.set_summary(session_id, "Some summary")

        manager.invalidate_summary(session_id)

        assert session_id not in manager._summary_cache

    def test_estimate_tokens(self, manager: ContextManager):
        """Test token estimation."""
        text = "Hello world"  # 11 chars
        tokens = manager._estimate_tokens(text)

        # ~4 chars per token
        assert 2 <= tokens <= 5


class TestSummarizationRequest:
    """Tests for SummarizationRequest dataclass."""

    def test_to_prompt(self):
        """Test prompt generation."""
        request = SummarizationRequest(
            session_id="test",
            messages=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
            max_tokens=100,
        )

        prompt = request.to_prompt()

        assert "user: Hello" in prompt
        assert "assistant: Hi there!" in prompt
        assert "100 tokens" in prompt
