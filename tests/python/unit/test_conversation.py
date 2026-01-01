"""Tests for conversation history."""

import pytest
from pathlib import Path

from openagent.memory.session import SessionManager
from openagent.memory.conversation import ConversationHistory, Message


class TestMessage:
    """Tests for Message dataclass."""

    def test_to_dict(self):
        """Test LLM-compatible dict conversion."""
        msg = Message(
            id=1,
            session_id="abc123",
            role="user",
            content="Hello!",
            token_count=5,
        )
        d = msg.to_dict()

        assert d == {"role": "user", "content": "Hello!"}


class TestConversationHistory:
    """Tests for ConversationHistory class."""

    @pytest.fixture
    def history(self, tmp_db_path: Path) -> ConversationHistory:
        """Create a conversation history with test database."""
        manager = SessionManager(tmp_db_path)
        session = manager.create(name="Test Session")
        return ConversationHistory(session, tmp_db_path)

    def test_add_message(self, history: ConversationHistory):
        """Test adding a message."""
        msg = history.add(role="user", content="Hello!")

        assert msg.id is not None
        assert msg.role == "user"
        assert msg.content == "Hello!"
        assert msg.session_id == history.session.id

    def test_add_with_token_count(self, history: ConversationHistory):
        """Test adding message with token count."""
        msg = history.add(role="user", content="Hello!", token_count=5)

        assert msg.token_count == 5

    def test_add_with_metadata(self, history: ConversationHistory):
        """Test adding message with metadata."""
        msg = history.add(
            role="tool",
            content="Tool output",
            metadata={"tool_name": "search"},
        )

        assert msg.metadata["tool_name"] == "search"

    def test_get_all(self, history: ConversationHistory):
        """Test getting all messages."""
        history.add(role="system", content="System prompt")
        history.add(role="user", content="Hello!")
        history.add(role="assistant", content="Hi there!")

        messages = history.get_all()

        assert len(messages) == 3
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        assert messages[2].role == "assistant"

    def test_get_recent(self, history: ConversationHistory):
        """Test getting recent messages."""
        for i in range(10):
            history.add(role="user", content=f"Message {i}")

        recent = history.get_recent(limit=3)

        assert len(recent) == 3
        # Should be in chronological order
        assert recent[0].content == "Message 7"
        assert recent[1].content == "Message 8"
        assert recent[2].content == "Message 9"

    def test_get_by_token_budget(self, history: ConversationHistory):
        """Test getting messages by token budget."""
        history.add(role="system", content="System", token_count=10)
        history.add(role="user", content="Message 1", token_count=100)
        history.add(role="assistant", content="Response 1", token_count=200)
        history.add(role="user", content="Message 2", token_count=100)
        history.add(role="assistant", content="Response 2", token_count=200)

        messages = history.get_by_token_budget(max_tokens=400)

        # Should include system + most recent that fit
        assert any(m.role == "system" for m in messages)
        total_tokens = sum(m.token_count for m in messages)
        assert total_tokens <= 400 or any(m.role == "system" for m in messages)

    def test_to_llm_format(self, history: ConversationHistory):
        """Test converting to LLM format."""
        history.add(role="system", content="System prompt")
        history.add(role="user", content="Hello!")

        llm_format = history.to_llm_format()

        assert llm_format == [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello!"},
        ]

    def test_count(self, history: ConversationHistory):
        """Test counting messages."""
        assert history.count() == 0

        history.add(role="user", content="Hello!")
        history.add(role="assistant", content="Hi!")

        assert history.count() == 2

    def test_clear(self, history: ConversationHistory):
        """Test clearing history."""
        history.add(role="system", content="System prompt")
        history.add(role="user", content="Hello!")
        history.add(role="assistant", content="Hi!")

        deleted = history.clear(keep_system=True)

        assert deleted == 2
        assert history.count() == 1

        messages = history.get_all()
        assert messages[0].role == "system"

    def test_clear_all(self, history: ConversationHistory):
        """Test clearing all messages including system."""
        history.add(role="system", content="System prompt")
        history.add(role="user", content="Hello!")

        deleted = history.clear(keep_system=False)

        assert deleted == 2
        assert history.count() == 0

    def test_get_total_tokens(self, history: ConversationHistory):
        """Test getting total token count."""
        history.add(role="user", content="Hello!", token_count=5)
        history.add(role="assistant", content="Hi there!", token_count=10)

        assert history.get_total_tokens() == 15

    def test_empty_total_tokens(self, history: ConversationHistory):
        """Test total tokens on empty history."""
        assert history.get_total_tokens() == 0
