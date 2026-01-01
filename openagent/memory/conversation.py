"""Conversation history management."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal
import json
import sqlite3

from openagent.memory.session import Session


Role = Literal["user", "assistant", "system", "tool"]


@dataclass
class Message:
    """A message in a conversation."""

    id: int
    session_id: str
    role: Role
    content: str
    token_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to LLM-compatible format."""
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_row(cls, row: tuple) -> "Message":
        """Create Message from database row."""
        return cls(
            id=row[0],
            session_id=row[1],
            role=row[2],
            content=row[3],
            token_count=row[4],
            created_at=datetime.fromisoformat(row[5]),
            metadata=json.loads(row[6]) if row[6] else {},
        )


class ConversationHistory:
    """Manages message history for a session."""

    def __init__(self, session: Session, db_path: Path | str):
        self.session = session
        self.db_path = Path(db_path)

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def add(
        self,
        role: Role,
        content: str,
        token_count: int = 0,
        metadata: dict | None = None,
    ) -> Message:
        """Add a message to the history."""
        now = datetime.now()

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages (session_id, role, content, token_count, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.session.id,
                    role,
                    content,
                    token_count,
                    now.isoformat(),
                    json.dumps(metadata or {}),
                ),
            )
            conn.commit()
            message_id = cursor.lastrowid

        return Message(
            id=message_id,
            session_id=self.session.id,
            role=role,
            content=content,
            token_count=token_count,
            created_at=now,
            metadata=metadata or {},
        )

    def get_all(self) -> list[Message]:
        """Get all messages in session, ordered by creation time."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                """,
                (self.session.id,),
            )
            return [Message.from_row(row) for row in cursor.fetchall()]

    def get_recent(self, limit: int = 20) -> list[Message]:
        """Get most recent messages."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT * FROM messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.session.id, limit),
            )
            # Reverse to get chronological order
            rows = cursor.fetchall()
            return [Message.from_row(row) for row in reversed(rows)]

    def get_by_token_budget(self, max_tokens: int) -> list[Message]:
        """
        Get messages that fit within token budget.

        Prioritizes most recent messages.
        """
        messages = self.get_all()
        result = []
        total_tokens = 0

        # Start from most recent
        for message in reversed(messages):
            if total_tokens + message.token_count <= max_tokens:
                result.insert(0, message)
                total_tokens += message.token_count
            elif message.role == "system":
                # Always include system messages
                result.insert(0, message)
                total_tokens += message.token_count

        return result

    def to_llm_format(self, messages: list[Message] | None = None) -> list[dict]:
        """Convert messages to LLM API format."""
        if messages is None:
            messages = self.get_all()
        return [m.to_dict() for m in messages]

    def count(self) -> int:
        """Get total message count in session."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ?",
                (self.session.id,),
            )
            return cursor.fetchone()[0]

    def clear(self, keep_system: bool = True) -> int:
        """
        Clear message history.

        Args:
            keep_system: If True, keep system messages

        Returns:
            Number of messages deleted
        """
        with self._get_conn() as conn:
            if keep_system:
                cursor = conn.execute(
                    "DELETE FROM messages WHERE session_id = ? AND role != 'system'",
                    (self.session.id,),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM messages WHERE session_id = ?",
                    (self.session.id,),
                )
            conn.commit()
            return cursor.rowcount

    def get_total_tokens(self) -> int:
        """Get total tokens used in this session."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT SUM(token_count) FROM messages WHERE session_id = ?",
                (self.session.id,),
            )
            result = cursor.fetchone()[0]
            return result or 0
