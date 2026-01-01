"""Main Agent orchestrator."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator

from openagent.core.llm import LLMClient, LLMResponse, AzureOpenAIClient
from openagent.core.intent import IntentRouter, Intent
from openagent.memory.session import Session, SessionManager
from openagent.memory.conversation import ConversationHistory
from openagent.memory.context import ContextManager, ContextConfig, ContextWindow
from openagent.telemetry.tokens import TokenTracker, TokenUsage


@dataclass
class AgentConfig:
    """Configuration for the Agent."""

    model: str = "gpt-4o-mini"
    api_endpoint: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    token_budget: int | None = None
    system_prompt: str = ""

    # Context management
    context_max_tokens: int = 8000
    context_recent_messages: int = 20


@dataclass
class Message:
    """A message in the conversation (in-memory)."""

    role: str  # user, assistant, system, tool
    content: str
    metadata: dict = field(default_factory=dict)


class Agent:
    """
    Main orchestrator that coordinates all components.

    Supports two modes:
    1. In-memory: Messages stored in memory only (default)
    2. Persistent: Messages stored in SQLite via ConversationHistory
    """

    def __init__(
        self,
        config: AgentConfig | None = None,
        llm_client: LLMClient | None = None,
        intent_router: IntentRouter | None = None,
        token_tracker: TokenTracker | None = None,
        # Persistent mode (optional)
        session: Session | None = None,
        conversation: ConversationHistory | None = None,
        context_manager: ContextManager | None = None,
    ):
        self.config = config or AgentConfig()
        self.llm = llm_client or AzureOpenAIClient(
            endpoint=self.config.api_endpoint,
            model=self.config.model,
        )
        self.intent_router = intent_router
        self.token_tracker = token_tracker

        # Persistent mode
        self.session = session
        self.conversation = conversation
        self.context_manager = context_manager or ContextManager(
            ContextConfig(
                max_tokens=self.config.context_max_tokens,
                recent_messages=self.config.context_recent_messages,
            )
        )

        # In-memory fallback
        self._messages: list[Message] = []
        if self.config.system_prompt:
            self._messages.append(
                Message(role="system", content=self.config.system_prompt)
            )

    @property
    def is_persistent(self) -> bool:
        """Check if agent is in persistent mode."""
        return self.conversation is not None

    def _get_context(self, user_message: str, rag_context: str | None = None) -> list[dict]:
        """Get context for LLM call."""
        if self.is_persistent:
            # Use context manager for smart context building
            window = self.context_manager.build(
                history=self.conversation,
                user_message=user_message,
                system_prompt=self.config.system_prompt,
                rag_context=rag_context,
            )
            return window.messages
        else:
            # In-memory mode - just use all messages
            messages = [{"role": m.role, "content": m.content} for m in self._messages]
            messages.append({"role": "user", "content": user_message})
            return messages

    def _record_message(self, role: str, content: str, token_count: int = 0) -> None:
        """Record message to storage."""
        if self.is_persistent:
            self.conversation.add(role=role, content=content, token_count=token_count)
        else:
            self._messages.append(Message(role=role, content=content))

    def _record_usage(self, response: LLMResponse) -> None:
        """Record token usage if tracker is available."""
        if self.token_tracker:
            usage = TokenUsage(
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                model=response.model,
                request_id=response.request_id,
            )
            self.token_tracker.record(usage)

    def chat_sync(
        self,
        message: str,
        rag_context: str | None = None,
    ) -> str:
        """
        Process user message synchronously.

        Args:
            message: User's input message
            rag_context: Optional context from RAG system

        Returns:
            Assistant's response text
        """
        # Build context
        context = self._get_context(message, rag_context)

        # Record user message
        self._record_message("user", message)

        # Call LLM
        response = self.llm.complete_sync(
            messages=context,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

        self._record_usage(response)

        # Record assistant response
        self._record_message(
            "assistant",
            response.content,
            token_count=response.output_tokens,
        )

        return response.content

    async def chat(
        self,
        message: str,
        rag_context: str | None = None,
    ) -> str:
        """
        Process user message asynchronously.

        Args:
            message: User's input message
            rag_context: Optional context from RAG system

        Returns:
            Assistant's response text
        """
        context = self._get_context(message, rag_context)
        self._record_message("user", message)

        response = await self.llm.complete(
            messages=context,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )

        self._record_usage(response)
        self._record_message(
            "assistant",
            response.content,
            token_count=response.output_tokens,
        )

        return response.content

    async def chat_stream(
        self,
        message: str,
        rag_context: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Process user message and stream response.

        Args:
            message: User's input message
            rag_context: Optional context from RAG system

        Yields:
            Chunks of the response as they arrive
        """
        context = self._get_context(message, rag_context)
        self._record_message("user", message)

        full_response = ""
        async for chunk in self.llm.stream(
            messages=context,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        ):
            full_response += chunk
            yield chunk

        self._record_message("assistant", full_response)

    async def chat_with_rag(
        self,
        message: str,
        rag_query: "RAGQuery | None" = None,
    ) -> str:
        """
        Process message with automatic RAG context retrieval.

        Args:
            message: User's input message
            rag_query: RAG query interface (optional)

        Returns:
            Assistant's response text
        """
        rag_context = None

        if rag_query:
            # Get intent to formulate better query
            intent = self.get_intent(message)
            query = intent.query if intent else message

            # Retrieve relevant context
            rag_context = rag_query.get_context_for_query(
                query,
                max_tokens=self.context_manager.config.max_rag_tokens,
            )

        return await self.chat(message, rag_context=rag_context)

    def get_intent(self, message: str) -> Intent | None:
        """
        Get the intent of a message without processing it.

        Returns None if no intent router is configured.
        """
        if not self.intent_router:
            return None

        # Get recent context
        if self.is_persistent:
            recent = self.conversation.get_recent(limit=5)
            context = "\n".join(f"{m.role}: {m.content}" for m in recent)
        else:
            context = "\n".join(
                f"{m.role}: {m.content}" for m in self._messages[-5:]
            )

        return self.intent_router.route(message, context)

    def clear_history(self, keep_system: bool = True) -> None:
        """Clear conversation history."""
        if self.is_persistent:
            self.conversation.clear(keep_system=keep_system)
            self.context_manager.invalidate_summary(self.session.id)
        else:
            if keep_system:
                self._messages = [m for m in self._messages if m.role == "system"]
            else:
                self._messages = []

    def get_history(self) -> list[dict]:
        """Get conversation history in LLM format."""
        if self.is_persistent:
            return self.conversation.to_llm_format()
        else:
            return [{"role": m.role, "content": m.content} for m in self._messages]

    def get_token_stats(self) -> dict:
        """Get token usage statistics."""
        if self.token_tracker:
            return self.token_tracker.get_session_stats().to_dict()
        return {}


def create_agent(
    db_path: Path | str,
    session_id: str | None = None,
    config: AgentConfig | None = None,
    **kwargs,
) -> Agent:
    """
    Factory to create an agent with persistent storage.

    Args:
        db_path: Path to SQLite database
        session_id: Existing session ID to load (creates new if None)
        config: Agent configuration
        **kwargs: Additional arguments passed to Agent

    Returns:
        Configured Agent instance
    """
    db_path = Path(db_path)
    config = config or AgentConfig()

    # Session management
    session_manager = SessionManager(db_path)

    if session_id:
        session = session_manager.load(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
    else:
        session = session_manager.create()

    # Components
    conversation = ConversationHistory(session, db_path)
    token_tracker = TokenTracker(session.id, db_path, budget=config.token_budget)
    context_manager = ContextManager(
        ContextConfig(
            max_tokens=config.context_max_tokens,
            recent_messages=config.context_recent_messages,
        )
    )

    return Agent(
        config=config,
        session=session,
        conversation=conversation,
        token_tracker=token_tracker,
        context_manager=context_manager,
        **kwargs,
    )
