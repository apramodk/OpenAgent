"""Session management with SQLite persistence."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import uuid


@dataclass
class Session:
    """A conversation session."""

    id: str
    name: str
    codebase_path: Path | None = None
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "codebase_path": str(self.codebase_path) if self.codebase_path else None,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_row(cls, row: tuple) -> "Session":
        """Create Session from database row."""
        return cls(
            id=row[0],
            name=row[1],
            codebase_path=Path(row[2]) if row[2] else None,
            created_at=datetime.fromisoformat(row[3]),
            last_accessed=datetime.fromisoformat(row[4]),
            metadata=json.loads(row[5]) if row[5] else {},
        )


class SessionManager:
    """Manages session lifecycle and persistence."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        codebase_path TEXT,
        created_at TEXT NOT NULL,
        last_accessed TEXT NOT NULL,
        metadata TEXT DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
        content TEXT NOT NULL,
        token_count INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        metadata TEXT DEFAULT '{}'
    );

    CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
    CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at);

    CREATE TABLE IF NOT EXISTS token_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
        input_tokens INTEGER NOT NULL,
        output_tokens INTEGER NOT NULL,
        model TEXT NOT NULL,
        cost_usd REAL,
        created_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_token_usage_session ON token_usage(session_id);
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA)
            conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create(
        self,
        name: str | None = None,
        codebase_path: Path | str | None = None,
        metadata: dict | None = None,
    ) -> Session:
        """Create a new session."""
        session_id = str(uuid.uuid4())[:8]
        now = datetime.now()

        if name is None:
            name = f"Session {now.strftime('%Y-%m-%d %H:%M')}"

        session = Session(
            id=session_id,
            name=name,
            codebase_path=Path(codebase_path) if codebase_path else None,
            created_at=now,
            last_accessed=now,
            metadata=metadata or {},
        )

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, name, codebase_path, created_at, last_accessed, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.id,
                    session.name,
                    str(session.codebase_path) if session.codebase_path else None,
                    session.created_at.isoformat(),
                    session.last_accessed.isoformat(),
                    json.dumps(session.metadata),
                ),
            )
            conn.commit()

        return session

    def load(self, session_id: str) -> Session | None:
        """Load an existing session by ID."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()

            if not row:
                return None

            # Update last_accessed
            new_accessed = datetime.now()
            conn.execute(
                "UPDATE sessions SET last_accessed = ? WHERE id = ?",
                (new_accessed.isoformat(), session_id),
            )
            conn.commit()

            # Return session with updated timestamp
            session = Session.from_row(row)
            session.last_accessed = new_accessed
            return session

    def list_all(self) -> list[Session]:
        """List all sessions, ordered by last accessed."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions ORDER BY last_accessed DESC"
            )
            return [Session.from_row(row) for row in cursor.fetchall()]

    def get_recent(self, limit: int = 10) -> list[Session]:
        """Get most recently accessed sessions."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions ORDER BY last_accessed DESC LIMIT ?",
                (limit,),
            )
            return [Session.from_row(row) for row in cursor.fetchall()]

    def delete(self, session_id: str) -> bool:
        """Delete a session and all associated data."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM sessions WHERE id = ?", (session_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def update(self, session: Session) -> None:
        """Update an existing session."""
        with self._get_conn() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET name = ?, codebase_path = ?, last_accessed = ?, metadata = ?
                WHERE id = ?
                """,
                (
                    session.name,
                    str(session.codebase_path) if session.codebase_path else None,
                    datetime.now().isoformat(),
                    json.dumps(session.metadata),
                    session.id,
                ),
            )
            conn.commit()
