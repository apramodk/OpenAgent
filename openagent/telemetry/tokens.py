"""Token usage tracking and cost estimation."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable
import sqlite3


# Pricing per 1M tokens (USD) - update as needed
MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI models
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    # Azure naming variants
    "gpt-4o-mini-2024-07-18": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo-2024-04-09": {"input": 10.0, "output": 30.0},
    # Anthropic models (for future use)
    "claude-3-opus": {"input": 15.0, "output": 75.0},
    "claude-3-sonnet": {"input": 3.0, "output": 15.0},
    "claude-3-haiku": {"input": 0.25, "output": 1.25},
}

# Default pricing for unknown models
DEFAULT_PRICING = {"input": 10.0, "output": 30.0}


@dataclass
class TokenUsage:
    """Token usage for a single request."""

    input_tokens: int
    output_tokens: int
    model: str
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: str = ""

    @property
    def total(self) -> int:
        """Total tokens used."""
        return self.input_tokens + self.output_tokens

    def estimated_cost(self) -> float:
        """Estimate cost in USD based on model pricing."""
        # Try exact match first
        pricing = MODEL_PRICING.get(self.model)

        # Try partial match (model names can have version suffixes)
        if not pricing:
            for model_name, model_pricing in MODEL_PRICING.items():
                if model_name in self.model or self.model in model_name:
                    pricing = model_pricing
                    break

        if not pricing:
            pricing = DEFAULT_PRICING

        input_cost = (self.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.output_tokens / 1_000_000) * pricing["output"]

        return input_cost + output_cost


@dataclass
class SessionTokenStats:
    """Aggregate token statistics for a session."""

    total_input: int = 0
    total_output: int = 0
    total_cost: float = 0.0
    request_count: int = 0

    @property
    def total_tokens(self) -> int:
        """Total tokens across all requests."""
        return self.total_input + self.total_output

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_input": self.total_input,
            "total_output": self.total_output,
            "total_tokens": self.total_tokens,
            "total_cost": round(self.total_cost, 4),
            "request_count": self.request_count,
        }


class TokenTracker:
    """Tracks token usage across a session."""

    def __init__(
        self,
        session_id: str,
        db_path: Path | str,
        budget: int | None = None,
    ):
        self.session_id = session_id
        self.db_path = Path(db_path)
        self.budget = budget
        self._listeners: list[Callable[[TokenUsage], None]] = []
        self._cache: SessionTokenStats | None = None

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def record(self, usage: TokenUsage, message_id: int | None = None) -> None:
        """Record token usage to database."""
        cost = usage.estimated_cost()

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO token_usage
                (session_id, message_id, input_tokens, output_tokens, model, cost_usd, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.session_id,
                    message_id,
                    usage.input_tokens,
                    usage.output_tokens,
                    usage.model,
                    cost,
                    usage.timestamp.isoformat(),
                ),
            )
            conn.commit()

        # Invalidate cache
        self._cache = None

        # Notify listeners
        self._notify(usage)

    def get_session_stats(self) -> SessionTokenStats:
        """Get aggregate stats for current session."""
        if self._cache is not None:
            return self._cache

        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT
                    COALESCE(SUM(input_tokens), 0),
                    COALESCE(SUM(output_tokens), 0),
                    COALESCE(SUM(cost_usd), 0),
                    COUNT(*)
                FROM token_usage
                WHERE session_id = ?
                """,
                (self.session_id,),
            )
            row = cursor.fetchone()

        self._cache = SessionTokenStats(
            total_input=row[0],
            total_output=row[1],
            total_cost=row[2],
            request_count=row[3],
        )

        return self._cache

    def get_budget_remaining(self) -> int | None:
        """Get remaining token budget, if set."""
        if self.budget is None:
            return None

        stats = self.get_session_stats()
        return max(0, self.budget - stats.total_tokens)

    def get_budget_percentage(self) -> float | None:
        """Get percentage of budget used (0-100)."""
        if self.budget is None:
            return None

        stats = self.get_session_stats()
        return min(100.0, (stats.total_tokens / self.budget) * 100)

    def is_over_budget(self) -> bool:
        """Check if session has exceeded budget."""
        remaining = self.get_budget_remaining()
        return remaining is not None and remaining <= 0

    def subscribe(self, callback: Callable[[TokenUsage], None]) -> None:
        """Subscribe to token usage updates."""
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[TokenUsage], None]) -> None:
        """Unsubscribe from token usage updates."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, usage: TokenUsage) -> None:
        """Notify all listeners of new usage."""
        for listener in self._listeners:
            try:
                listener(usage)
            except Exception:
                pass  # Don't let listener errors break the tracker

    def get_usage_history(self, limit: int = 100) -> list[TokenUsage]:
        """Get recent token usage records."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                SELECT input_tokens, output_tokens, model, created_at
                FROM token_usage
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (self.session_id, limit),
            )
            return [
                TokenUsage(
                    input_tokens=row[0],
                    output_tokens=row[1],
                    model=row[2],
                    timestamp=datetime.fromisoformat(row[3]),
                )
                for row in cursor.fetchall()
            ]
