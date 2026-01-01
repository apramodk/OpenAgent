"""Tests for session management."""

import pytest
from datetime import datetime
from pathlib import Path

from openagent.memory.session import Session, SessionManager


class TestSession:
    """Tests for Session dataclass."""

    def test_to_dict(self):
        """Test dictionary conversion."""
        session = Session(
            id="abc123",
            name="Test Session",
            codebase_path=Path("/home/user/project"),
            metadata={"key": "value"},
        )
        d = session.to_dict()

        assert d["id"] == "abc123"
        assert d["name"] == "Test Session"
        assert d["codebase_path"] == "/home/user/project"
        assert d["metadata"] == {"key": "value"}
        assert "created_at" in d
        assert "last_accessed" in d

    def test_from_row(self):
        """Test creation from database row."""
        now = datetime.now().isoformat()
        row = ("abc123", "Test Session", "/home/user/project", now, now, '{"key": "value"}')

        session = Session.from_row(row)

        assert session.id == "abc123"
        assert session.name == "Test Session"
        assert session.codebase_path == Path("/home/user/project")
        assert session.metadata == {"key": "value"}

    def test_from_row_null_codebase(self):
        """Test creation from row with null codebase path."""
        now = datetime.now().isoformat()
        row = ("abc123", "Test Session", None, now, now, None)

        session = Session.from_row(row)

        assert session.codebase_path is None
        assert session.metadata == {}


class TestSessionManager:
    """Tests for SessionManager class."""

    @pytest.fixture
    def manager(self, tmp_db_path: Path) -> SessionManager:
        """Create a session manager with test database."""
        return SessionManager(tmp_db_path)

    def test_create_session(self, manager: SessionManager):
        """Test creating a new session."""
        session = manager.create(name="Test Session")

        assert session.id is not None
        assert session.name == "Test Session"
        assert len(session.id) == 8

    def test_create_session_default_name(self, manager: SessionManager):
        """Test creating session with default name."""
        session = manager.create()

        assert session.name.startswith("Session ")

    def test_create_with_codebase_path(self, manager: SessionManager):
        """Test creating session with codebase path."""
        session = manager.create(
            name="Project Session",
            codebase_path="/home/user/project",
        )

        assert session.codebase_path == Path("/home/user/project")

    def test_create_with_metadata(self, manager: SessionManager):
        """Test creating session with metadata."""
        session = manager.create(
            name="Test",
            metadata={"model": "gpt-4", "temperature": 0.7},
        )

        assert session.metadata["model"] == "gpt-4"
        assert session.metadata["temperature"] == 0.7

    def test_load_session(self, manager: SessionManager):
        """Test loading an existing session."""
        created = manager.create(name="Test Session")
        loaded = manager.load(created.id)

        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.name == created.name

    def test_load_nonexistent(self, manager: SessionManager):
        """Test loading a nonexistent session."""
        loaded = manager.load("nonexistent")
        assert loaded is None

    def test_load_updates_last_accessed(self, manager: SessionManager):
        """Test that loading updates last_accessed timestamp."""
        session = manager.create(name="Test")
        original_accessed = session.last_accessed

        # Small delay to ensure timestamp changes
        import time
        time.sleep(0.01)

        loaded = manager.load(session.id)
        assert loaded.last_accessed > original_accessed

    def test_list_all(self, manager: SessionManager):
        """Test listing all sessions."""
        manager.create(name="Session 1")
        manager.create(name="Session 2")
        manager.create(name="Session 3")

        sessions = manager.list_all()

        assert len(sessions) == 3
        # Should be ordered by last_accessed DESC
        assert sessions[0].name == "Session 3"

    def test_get_recent(self, manager: SessionManager):
        """Test getting recent sessions with limit."""
        for i in range(5):
            manager.create(name=f"Session {i}")

        recent = manager.get_recent(limit=3)

        assert len(recent) == 3

    def test_delete_session(self, manager: SessionManager):
        """Test deleting a session."""
        session = manager.create(name="To Delete")

        deleted = manager.delete(session.id)
        assert deleted is True

        loaded = manager.load(session.id)
        assert loaded is None

    def test_delete_nonexistent(self, manager: SessionManager):
        """Test deleting nonexistent session."""
        deleted = manager.delete("nonexistent")
        assert deleted is False

    def test_update_session(self, manager: SessionManager):
        """Test updating a session."""
        session = manager.create(name="Original Name")
        session.name = "Updated Name"
        session.metadata = {"updated": True}

        manager.update(session)

        loaded = manager.load(session.id)
        assert loaded.name == "Updated Name"
        assert loaded.metadata["updated"] is True

    def test_database_persistence(self, tmp_db_path: Path):
        """Test that sessions persist across manager instances."""
        manager1 = SessionManager(tmp_db_path)
        session = manager1.create(name="Persistent")

        # Create new manager instance
        manager2 = SessionManager(tmp_db_path)
        loaded = manager2.load(session.id)

        assert loaded is not None
        assert loaded.name == "Persistent"
