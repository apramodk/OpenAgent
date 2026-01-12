"""Intent extraction and routing using DSPy."""

from dataclasses import dataclass
from enum import Enum
from typing import Literal
import os

import dspy
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


class IntentType(Enum):
    """Types of user intent."""

    RESEARCH = "research"  # Query RAG/search to learn about code
    ORGANIZE = "organize"  # Structure ideas, notes, plans
    CONTROL = "control"  # Execute actions (write code, run commands)


ActionType = Literal["search", "clarify", "answer", "execute"]


@dataclass
class Intent:
    """Extracted user intent."""

    type: IntentType
    entities: list[str]
    action: ActionType
    query: str  # Reformulated query for RAG
    reasoning: str
    confidence: float = 1.0

    @classmethod
    def from_dict(cls, data: dict) -> "Intent":
        """Create Intent from dictionary."""
        intent_type = data.get("intent_type", "research")
        if intent_type in ("research", "organize", "control"):
            type_enum = IntentType(intent_type)
        else:
            type_enum = IntentType.RESEARCH

        entities = data.get("entities", [])
        if isinstance(entities, str):
            entities = [e.strip() for e in entities.split(",") if e.strip()]

        return cls(
            type=type_enum,
            entities=entities,
            action=data.get("action", "search"),
            query=data.get("query", ""),
            reasoning=data.get("reasoning", ""),
            confidence=data.get("confidence", 1.0),
        )


class ExtractIntent(dspy.Signature):
    """Extract user intent from message."""

    user_input: str = dspy.InputField(desc="The user's message")
    context: str = dspy.InputField(
        default="", desc="Previous conversation context"
    )

    intent_type: str = dspy.OutputField(
        desc="One of: research, organize, control"
    )
    entities: str = dspy.OutputField(
        desc="Comma-separated key terms, functions, files mentioned"
    )
    action: str = dspy.OutputField(
        desc="One of: search (query RAG), clarify (ask user), answer (respond directly), execute (run action)"
    )
    query: str = dspy.OutputField(
        desc="Reformulated search query if action is search, otherwise empty"
    )


class IntentRouter:
    """Routes user messages to appropriate handlers based on intent."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
    ):
        load_dotenv()

        model = model or os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
        api_key = api_key or os.environ.get("AZURE_KEY", "")
        api_base = api_base or os.environ.get("PROJECT_ENDPOINT_OAI", "")

        lm = dspy.LM(
            f"azure/{model}",
            api_key=api_key,
            api_base=api_base,
            api_version="2024-02-01",
        )
        dspy.configure(lm=lm)

        self._extractor = dspy.ChainOfThought(ExtractIntent)

    def route(self, message: str, context: str = "") -> Intent:
        """Extract intent from user message."""
        result = self._extractor(user_input=message, context=context)

        return Intent.from_dict(
            {
                "intent_type": result.intent_type,
                "entities": result.entities,
                "action": result.action,
                "query": result.query,
                "reasoning": getattr(result, "reasoning", ""),
            }
        )

    def route_batch(
        self, messages: list[tuple[str, str]]
    ) -> list[Intent]:
        """Route multiple messages (message, context) pairs."""
        return [self.route(msg, ctx) for msg, ctx in messages]
