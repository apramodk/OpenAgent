"""Tests for JSON-RPC handler implementations.

## Test Classification

| Category | Tests | Description |
|----------|-------|-------------|
| Session Handlers | 5 | Create, load, list, delete sessions |
| Token Handlers | 3 | Get stats, set budget |
| Chat Handlers | 2 | Send message, cancel (stub) |
| Error Handling | 3 | Missing params, not found, uninitialized |
"""

import pytest
from pathlib import Path

from openagent.server.handlers import Handlers, create_handlers
from openagent.memory.session import SessionManager


class TestHandlers:
    """Tests for Handlers class."""

    @pytest.fixture
    def handlers(self, tmp_db_path: Path) -> Handlers:
        """Create handlers with test database."""
        session_manager = SessionManager(tmp_db_path)
        return Handlers(session_manager=session_manager)

    @pytest.mark.asyncio
    async def test_session_create(self, handlers: Handlers):
        """Test creating a new session."""
        result = await handlers.session_create({
            "name": "Test Session",
        })

        assert "id" in result
        assert result["name"] == "Test Session"

    @pytest.mark.asyncio
    async def test_session_create_with_codebase(self, handlers: Handlers):
        """Test creating session with codebase path."""
        result = await handlers.session_create({
            "name": "Project",
            "codebase_path": "/home/user/project",
        })

        assert result["codebase_path"] == "/home/user/project"

    @pytest.mark.asyncio
    async def test_session_load(self, handlers: Handlers):
        """Test loading an existing session."""
        # Create first
        created = await handlers.session_create({"name": "LoadMe"})
        session_id = created["id"]

        # Load
        result = await handlers.session_load({"id": session_id})

        assert result["id"] == session_id
        assert result["name"] == "LoadMe"

    @pytest.mark.asyncio
    async def test_session_load_not_found(self, handlers: Handlers):
        """Test loading nonexistent session."""
        result = await handlers.session_load({"id": "nonexistent"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_session_load_missing_id(self, handlers: Handlers):
        """Test loading without ID."""
        result = await handlers.session_load({})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_session_list(self, handlers: Handlers):
        """Test listing sessions."""
        # Create some sessions
        await handlers.session_create({"name": "Session 1"})
        await handlers.session_create({"name": "Session 2"})

        result = await handlers.session_list({})

        assert "sessions" in result
        assert len(result["sessions"]) == 2

    @pytest.mark.asyncio
    async def test_session_list_with_limit(self, handlers: Handlers):
        """Test listing sessions with limit."""
        for i in range(5):
            await handlers.session_create({"name": f"Session {i}"})

        result = await handlers.session_list({"limit": 3})

        assert len(result["sessions"]) == 3

    @pytest.mark.asyncio
    async def test_session_delete(self, handlers: Handlers):
        """Test deleting a session."""
        created = await handlers.session_create({"name": "DeleteMe"})
        session_id = created["id"]

        result = await handlers.session_delete({"id": session_id})

        assert result["deleted"] is True

        # Verify it's gone
        load_result = await handlers.session_load({"id": session_id})
        assert "error" in load_result

    @pytest.mark.asyncio
    async def test_tokens_get_no_tracker(self, handlers: Handlers):
        """Test getting tokens without tracker initialized."""
        result = await handlers.tokens_get({})

        assert result["total_tokens"] == 0
        assert result["request_count"] == 0

    @pytest.mark.asyncio
    async def test_tokens_get_with_session(self, handlers: Handlers):
        """Test getting tokens after session is loaded."""
        # Create and load a session (initializes token tracker)
        created = await handlers.session_create({"name": "Test"})
        await handlers.session_load({"id": created["id"]})

        result = await handlers.tokens_get({})

        assert "total_input" in result
        assert "total_output" in result
        assert "total_cost" in result

    @pytest.mark.asyncio
    async def test_tokens_set_budget(self, handlers: Handlers):
        """Test setting token budget."""
        # Create and load session first
        created = await handlers.session_create({"name": "Test"})
        await handlers.session_load({"id": created["id"]})

        result = await handlers.tokens_set_budget({"budget": 10000})

        assert result["budget"] == 10000

    @pytest.mark.asyncio
    async def test_chat_send_no_agent(self, handlers: Handlers):
        """Test chat without agent initialized."""
        result = await handlers.chat_send({"message": "Hello"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_chat_send_empty_message(self, handlers: Handlers):
        """Test chat with empty message."""
        # Initialize session
        created = await handlers.session_create({"name": "Test"})
        await handlers.session_load({"id": created["id"]})

        result = await handlers.chat_send({"message": ""})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_chat_cancel(self, handlers: Handlers):
        """Test chat cancellation (stub)."""
        result = await handlers.chat_cancel({})

        assert result["cancelled"] is False  # Not implemented yet

    @pytest.mark.asyncio
    async def test_tools_list(self, handlers: Handlers):
        """Test listing tools (stub)."""
        result = await handlers.tools_list({})

        assert result["tools"] == []


class TestCreateHandlers:
    """Tests for create_handlers factory function."""

    def test_create_handlers_default_path(self, tmp_path: Path, monkeypatch):
        """Test creating handlers with default path."""
        # Monkeypatch home to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))

        handlers = create_handlers()

        assert "chat.send" in handlers
        assert "session.create" in handlers
        assert "tokens.get" in handlers

    def test_create_handlers_custom_path(self, tmp_db_path: Path):
        """Test creating handlers with custom path."""
        handlers = create_handlers(db_path=tmp_db_path)

        assert "chat.send" in handlers
        assert "session.create" in handlers

    def test_all_methods_registered(self, tmp_db_path: Path):
        """Test all expected methods are registered."""
        handlers = create_handlers(db_path=tmp_db_path)

        expected_methods = [
            "chat.send",
            "chat.cancel",
            "session.create",
            "session.load",
            "session.list",
            "session.delete",
            "tokens.get",
            "tokens.set_budget",
            "tools.list",
            "tools.call",
        ]

        for method in expected_methods:
            assert method in handlers, f"Missing handler for {method}"
