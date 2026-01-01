"""Tests for token tracking."""

import pytest
from datetime import datetime
from pathlib import Path

from openagent.telemetry.tokens import (
    TokenUsage,
    TokenTracker,
    SessionTokenStats,
    MODEL_PRICING,
)
from openagent.memory.session import SessionManager


class TestTokenUsage:
    """Tests for TokenUsage dataclass."""

    def test_total_calculation(self):
        """Test total tokens calculation."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=200,
            model="gpt-4o-mini",
        )
        assert usage.total == 300

    def test_cost_estimation_gpt4o_mini(self):
        """Test cost estimation for gpt-4o-mini."""
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="gpt-4o-mini",
        )
        # $0.15/M input + $0.60/M output = $0.75
        assert usage.estimated_cost() == pytest.approx(0.75, rel=0.01)

    def test_cost_estimation_gpt4(self):
        """Test cost estimation for gpt-4."""
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="gpt-4",
        )
        # $30/M input + $60/M output = $90
        assert usage.estimated_cost() == pytest.approx(90.0, rel=0.01)

    def test_cost_estimation_unknown_model(self):
        """Test cost estimation for unknown model uses default pricing."""
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="unknown-model-xyz",
        )
        # Should use default pricing ($10/M input + $30/M output = $40)
        assert usage.estimated_cost() == pytest.approx(40.0, rel=0.01)

    def test_cost_estimation_partial_model_match(self):
        """Test cost estimation with model name containing version suffix."""
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="gpt-4o-mini-2024-07-18",
        )
        # Should match gpt-4o-mini pricing
        assert usage.estimated_cost() == pytest.approx(0.75, rel=0.01)

    def test_zero_tokens(self):
        """Test with zero tokens."""
        usage = TokenUsage(
            input_tokens=0,
            output_tokens=0,
            model="gpt-4o-mini",
        )
        assert usage.total == 0
        assert usage.estimated_cost() == 0.0

    def test_timestamp_default(self):
        """Test that timestamp is set by default."""
        before = datetime.now()
        usage = TokenUsage(input_tokens=100, output_tokens=200, model="gpt-4o-mini")
        after = datetime.now()

        assert before <= usage.timestamp <= after


class TestSessionTokenStats:
    """Tests for SessionTokenStats dataclass."""

    def test_total_tokens(self):
        """Test total tokens calculation."""
        stats = SessionTokenStats(
            total_input=500,
            total_output=1000,
            total_cost=0.05,
            request_count=3,
        )
        assert stats.total_tokens == 1500

    def test_to_dict(self):
        """Test dictionary conversion."""
        stats = SessionTokenStats(
            total_input=500,
            total_output=1000,
            total_cost=0.05123,
            request_count=3,
        )
        d = stats.to_dict()

        assert d["total_input"] == 500
        assert d["total_output"] == 1000
        assert d["total_tokens"] == 1500
        assert d["total_cost"] == 0.0512  # Rounded to 4 decimals
        assert d["request_count"] == 3


class TestTokenTracker:
    """Tests for TokenTracker class."""

    @pytest.fixture
    def tracker(self, tmp_db_path: Path) -> TokenTracker:
        """Create a token tracker with test database."""
        # Initialize the database schema first
        session_mgr = SessionManager(tmp_db_path)
        session = session_mgr.create(name="test-session")
        return TokenTracker(session.id, tmp_db_path)

    def test_record_and_retrieve(self, tracker: TokenTracker):
        """Test recording and retrieving token usage."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=200,
            model="gpt-4o-mini",
        )
        tracker.record(usage)

        stats = tracker.get_session_stats()
        assert stats.total_input == 100
        assert stats.total_output == 200
        assert stats.request_count == 1
        assert stats.total_cost > 0

    def test_multiple_records(self, tracker: TokenTracker):
        """Test recording multiple usages."""
        for i in range(3):
            usage = TokenUsage(
                input_tokens=100,
                output_tokens=200,
                model="gpt-4o-mini",
            )
            tracker.record(usage)

        stats = tracker.get_session_stats()
        assert stats.total_input == 300
        assert stats.total_output == 600
        assert stats.request_count == 3

    def test_budget_tracking(self, tracker: TokenTracker):
        """Test budget tracking."""
        tracker.budget = 1000

        usage = TokenUsage(
            input_tokens=300,
            output_tokens=200,
            model="gpt-4o-mini",
        )
        tracker.record(usage)

        assert tracker.get_budget_remaining() == 500
        assert tracker.get_budget_percentage() == pytest.approx(50.0)
        assert not tracker.is_over_budget()

    def test_over_budget(self, tracker: TokenTracker):
        """Test over budget detection."""
        tracker.budget = 100

        usage = TokenUsage(
            input_tokens=300,
            output_tokens=200,
            model="gpt-4o-mini",
        )
        tracker.record(usage)

        assert tracker.get_budget_remaining() == 0
        assert tracker.is_over_budget()

    def test_no_budget(self, tracker: TokenTracker):
        """Test when no budget is set."""
        assert tracker.budget is None
        assert tracker.get_budget_remaining() is None
        assert tracker.get_budget_percentage() is None
        assert not tracker.is_over_budget()

    def test_subscriber_notification(self, tracker: TokenTracker):
        """Test subscriber notification on record."""
        received: list[TokenUsage] = []
        tracker.subscribe(lambda u: received.append(u))

        usage = TokenUsage(
            input_tokens=100,
            output_tokens=200,
            model="gpt-4o-mini",
        )
        tracker.record(usage)

        assert len(received) == 1
        assert received[0].total == 300

    def test_unsubscribe(self, tracker: TokenTracker):
        """Test unsubscribing from notifications."""
        received: list[TokenUsage] = []
        callback = lambda u: received.append(u)

        tracker.subscribe(callback)
        tracker.unsubscribe(callback)

        usage = TokenUsage(input_tokens=100, output_tokens=200, model="gpt-4o-mini")
        tracker.record(usage)

        assert len(received) == 0

    def test_get_usage_history(self, tracker: TokenTracker):
        """Test retrieving usage history."""
        for i in range(5):
            usage = TokenUsage(
                input_tokens=100 * (i + 1),
                output_tokens=200,
                model="gpt-4o-mini",
            )
            tracker.record(usage)

        history = tracker.get_usage_history(limit=3)
        assert len(history) == 3
        # Most recent first
        assert history[0].input_tokens == 500
        assert history[1].input_tokens == 400
        assert history[2].input_tokens == 300

    def test_cache_invalidation(self, tracker: TokenTracker):
        """Test that cache is invalidated on new record."""
        usage1 = TokenUsage(input_tokens=100, output_tokens=200, model="gpt-4o-mini")
        tracker.record(usage1)

        stats1 = tracker.get_session_stats()
        assert stats1.total_tokens == 300

        usage2 = TokenUsage(input_tokens=100, output_tokens=200, model="gpt-4o-mini")
        tracker.record(usage2)

        stats2 = tracker.get_session_stats()
        assert stats2.total_tokens == 600
