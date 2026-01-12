"""Tests for intent extraction."""

import pytest

from openagent.core.intent import Intent, IntentType


class TestIntent:
    """Tests for Intent dataclass."""

    def test_from_dict_research(self):
        """Test creating research intent from dict."""
        data = {
            "intent_type": "research",
            "entities": "auth, login, token",
            "action": "search",
            "query": "How does authentication work?",
            "reasoning": "User wants to understand auth flow",
        }

        intent = Intent.from_dict(data)

        assert intent.type == IntentType.RESEARCH
        assert intent.entities == ["auth", "login", "token"]
        assert intent.action == "search"
        assert intent.query == "How does authentication work?"
        assert intent.reasoning == "User wants to understand auth flow"

    def test_from_dict_organize(self):
        """Test creating organize intent from dict."""
        data = {
            "intent_type": "organize",
            "entities": ["notes", "ideas"],
            "action": "answer",
            "query": "",
            "reasoning": "User wants to structure their thoughts",
        }

        intent = Intent.from_dict(data)

        assert intent.type == IntentType.ORGANIZE
        assert intent.action == "answer"

    def test_from_dict_control(self):
        """Test creating control intent from dict."""
        data = {
            "intent_type": "control",
            "entities": "main.py",
            "action": "execute",
            "query": "",
            "reasoning": "User wants to run code",
        }

        intent = Intent.from_dict(data)

        assert intent.type == IntentType.CONTROL
        assert intent.action == "execute"

    def test_from_dict_unknown_type(self):
        """Test fallback to research for unknown type."""
        data = {
            "intent_type": "unknown_type",
            "entities": "",
            "action": "search",
            "query": "query",
            "reasoning": "",
        }

        intent = Intent.from_dict(data)

        assert intent.type == IntentType.RESEARCH

    def test_from_dict_entities_list(self):
        """Test entities as list."""
        data = {
            "intent_type": "research",
            "entities": ["auth", "login"],
            "action": "search",
            "query": "query",
            "reasoning": "",
        }

        intent = Intent.from_dict(data)

        assert intent.entities == ["auth", "login"]

    def test_from_dict_entities_string(self):
        """Test entities as comma-separated string."""
        data = {
            "intent_type": "research",
            "entities": "auth, login, token",
            "action": "search",
            "query": "query",
            "reasoning": "",
        }

        intent = Intent.from_dict(data)

        assert intent.entities == ["auth", "login", "token"]

    def test_from_dict_empty_entities(self):
        """Test empty entities."""
        data = {
            "intent_type": "research",
            "entities": "",
            "action": "search",
            "query": "query",
            "reasoning": "",
        }

        intent = Intent.from_dict(data)

        assert intent.entities == []

    def test_from_dict_defaults(self):
        """Test default values."""
        data = {}

        intent = Intent.from_dict(data)

        assert intent.type == IntentType.RESEARCH
        assert intent.entities == []
        assert intent.action == "search"
        assert intent.query == ""
        assert intent.reasoning == ""
        assert intent.confidence == 1.0

    def test_from_dict_with_confidence(self):
        """Test custom confidence score."""
        data = {
            "intent_type": "research",
            "entities": "",
            "action": "search",
            "query": "query",
            "reasoning": "",
            "confidence": 0.85,
        }

        intent = Intent.from_dict(data)

        assert intent.confidence == 0.85


class TestIntentType:
    """Tests for IntentType enum."""

    def test_values(self):
        """Test enum values."""
        assert IntentType.RESEARCH.value == "research"
        assert IntentType.ORGANIZE.value == "organize"
        assert IntentType.CONTROL.value == "control"

    def test_from_string(self):
        """Test creating from string."""
        assert IntentType("research") == IntentType.RESEARCH
        assert IntentType("organize") == IntentType.ORGANIZE
        assert IntentType("control") == IntentType.CONTROL
