"""Tests for JSON-RPC handler implementations.

## Test Classification

| Category | Tests | Description |
|----------|-------|-------------|
| Session Handlers | 5 | Create, load, list, delete sessions |
| Token Handlers | 3 | Get stats, set budget |
| Chat Handlers | 2 | Send message, cancel (stub) |
| RAG Handlers | 4 | Embeddings, status, search |
| Error Handling | 3 | Missing params, not found, uninitialized |
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from openagent.server.handlers import Handlers, create_handlers
from openagent.memory.session import SessionManager
from openagent.rag.store import RAGStore, Chunk, ChunkMetadata


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
            "rag.embeddings",
            "rag.status",
            "rag.search",
        ]

        for method in expected_methods:
            assert method in handlers, f"Missing handler for {method}"


class TestRagEmbeddings:
    """Tests for RAG embeddings endpoint."""

    @pytest.fixture
    def mock_rag_store(self, tmp_path: Path):
        """Create a mock RAG store with test data."""
        store = MagicMock(spec=RAGStore)

        # Mock the _collection.get() method to return test embeddings
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": ["chunk1", "chunk2", "chunk3"],
            "embeddings": [
                [0.1, 0.2, 0.3, 0.4],  # 4-dim embeddings for testing
                [0.5, 0.6, 0.7, 0.8],
                [0.9, 0.1, 0.2, 0.3],
            ],
            "metadatas": [
                {"path": "src/main.py", "type": "function"},
                {"path": "src/utils.py", "type": "class"},
                {"path": "src/lib.py", "type": "module"},
            ],
        }
        store._collection = mock_collection
        return store

    @pytest.fixture
    def handlers_with_rag(self, tmp_db_path: Path, mock_rag_store) -> Handlers:
        """Create handlers with mock RAG store."""
        session_manager = SessionManager(tmp_db_path)
        return Handlers(
            session_manager=session_manager,
            rag_store=mock_rag_store,
        )

    @pytest.mark.asyncio
    async def test_rag_embeddings_returns_points(self, handlers_with_rag: Handlers):
        """Test that rag_embeddings returns projected 2D points."""
        result = await handlers_with_rag.rag_embeddings({})

        assert "points" in result
        assert "count" in result
        assert result["count"] == 3
        assert len(result["points"]) == 3

    @pytest.mark.asyncio
    async def test_rag_embeddings_point_structure(self, handlers_with_rag: Handlers):
        """Test that each point has required fields."""
        result = await handlers_with_rag.rag_embeddings({})

        for point in result["points"]:
            assert "id" in point
            assert "x" in point
            assert "y" in point
            assert "path" in point
            assert "type" in point
            # x and y should be normalized to 0-1
            assert 0 <= point["x"] <= 1
            assert 0 <= point["y"] <= 1

    @pytest.mark.asyncio
    async def test_rag_embeddings_preserves_metadata(self, handlers_with_rag: Handlers):
        """Test that metadata is preserved in points."""
        result = await handlers_with_rag.rag_embeddings({})

        ids = [p["id"] for p in result["points"]]
        assert "chunk1" in ids
        assert "chunk2" in ids
        assert "chunk3" in ids

        # Find chunk1 and verify its metadata
        chunk1 = next(p for p in result["points"] if p["id"] == "chunk1")
        assert chunk1["path"] == "src/main.py"
        assert chunk1["type"] == "function"

    @pytest.mark.asyncio
    async def test_rag_embeddings_no_store(self, tmp_db_path: Path):
        """Test rag_embeddings when RAG store is not initialized."""
        session_manager = SessionManager(tmp_db_path)
        handlers = Handlers(session_manager=session_manager, rag_store=None)

        result = await handlers.rag_embeddings({})

        assert "error" in result
        assert result["points"] == []

    @pytest.mark.asyncio
    async def test_rag_embeddings_empty_collection(self, tmp_db_path: Path):
        """Test rag_embeddings with empty collection."""
        store = MagicMock(spec=RAGStore)
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            "ids": [],
            "embeddings": [],
            "metadatas": [],
        }
        store._collection = mock_collection

        session_manager = SessionManager(tmp_db_path)
        handlers = Handlers(session_manager=session_manager, rag_store=store)

        result = await handlers.rag_embeddings({})

        assert result["points"] == []
        assert result["count"] == 0


class TestStreamingTokens:
    """Tests for streaming with token stats in done notification."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent that streams responses."""
        agent = MagicMock()

        # Mock chat_stream to yield chunks
        async def mock_stream(*args, **kwargs):
            yield "Hello"
            yield " world"
            yield "!"

        agent.chat_stream = mock_stream
        agent.get_intent.return_value = None

        # Mock token tracker
        mock_stats = MagicMock()
        mock_stats.to_dict.return_value = {
            "total_input": 10,
            "total_output": 20,
            "total_tokens": 30,
            "total_cost": 0.001,
            "request_count": 1,
        }
        agent.token_tracker = MagicMock()
        agent.token_tracker.get_session_stats.return_value = mock_stats

        return agent

    @pytest.mark.asyncio
    async def test_streaming_done_includes_tokens(self, tmp_db_path: Path, mock_agent):
        """Test that streaming done notification includes token stats."""
        notifications = []

        async def capture_notify(method: str, params: dict):
            notifications.append((method, params))

        session_manager = SessionManager(tmp_db_path)
        handlers = Handlers(
            session_manager=session_manager,
            agent=mock_agent,
            notify=capture_notify,
        )

        result = await handlers.chat_send({"message": "test", "stream": True})

        # Find the done notification
        done_notifications = [
            (m, p) for m, p in notifications
            if m == "chat.stream" and p.get("done")
        ]

        assert len(done_notifications) == 1
        method, params = done_notifications[0]

        assert params["done"] is True
        assert "tokens" in params
        assert params["tokens"]["total_tokens"] == 30
        assert params["tokens"]["total_input"] == 10
        assert params["tokens"]["total_output"] == 20

    @pytest.mark.asyncio
    async def test_streaming_sends_chunks(self, tmp_db_path: Path, mock_agent):
        """Test that streaming sends chunk notifications."""
        notifications = []

        async def capture_notify(method: str, params: dict):
            notifications.append((method, params))

        session_manager = SessionManager(tmp_db_path)
        handlers = Handlers(
            session_manager=session_manager,
            agent=mock_agent,
            notify=capture_notify,
        )

        await handlers.chat_send({"message": "test", "stream": True})

        # Should have chunk notifications
        chunk_notifications = [
            p for m, p in notifications
            if m == "chat.stream" and "chunk" in p
        ]

        assert len(chunk_notifications) == 3
        chunks = [p["chunk"] for p in chunk_notifications]
        assert chunks == ["Hello", " world", "!"]
