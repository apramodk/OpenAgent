"""OpenAgent - Token-efficient AI assistant for navigating large codebases."""

__version__ = "0.1.0"

from openagent.core.agent import Agent
from openagent.core.intent import IntentRouter, Intent, IntentType

__all__ = ["Agent", "IntentRouter", "Intent", "IntentType", "__version__"]
