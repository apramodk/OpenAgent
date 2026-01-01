"""Context window management for LLM calls.

Handles:
- Sliding window of recent messages
- Token budget constraints
- System prompt preservation
- RAG context injection
- Summarization of older context
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openagent.memory.conversation import Message, ConversationHistory


@dataclass
class ContextConfig:
    """Configuration for context management."""

    # Token limits
    max_tokens: int = 8000
    reserved_for_response: int = 1000  # Reserve tokens for LLM response

    # Message selection
    recent_messages: int = 20  # Keep last N messages before applying token budget
    always_include_system: bool = True

    # Summarization
    summarize_after: int = 30  # Summarize after N messages
    summary_max_tokens: int = 500

    # RAG
    max_rag_tokens: int = 2000
    max_rag_chunks: int = 5

    @property
    def available_for_context(self) -> int:
        """Tokens available for context (excluding response reserve)."""
        return self.max_tokens - self.reserved_for_response


@dataclass
class ContextWindow:
    """A prepared context window for LLM consumption."""

    messages: list[dict] = field(default_factory=list)
    total_tokens: int = 0
    included_message_count: int = 0
    truncated: bool = False
    has_summary: bool = False
    rag_chunks_used: int = 0

    def to_llm_format(self) -> list[dict]:
        """Get messages in LLM API format."""
        return self.messages


class ContextManager:
    """Builds optimal context windows for LLM calls."""

    def __init__(self, config: ContextConfig | None = None):
        self.config = config or ContextConfig()
        self._summary_cache: dict[str, str] = {}  # session_id -> summary

    def build(
        self,
        history: "ConversationHistory",
        user_message: str,
        system_prompt: str | None = None,
        rag_context: str | None = None,
    ) -> ContextWindow:
        """
        Build an optimal context window.

        Priority order:
        1. System prompt (always first)
        2. Summary of old messages (if exists)
        3. RAG context (injected as system message)
        4. Recent messages (as many as fit)
        5. Current user message

        Args:
            history: Conversation history
            user_message: Current user message to include
            system_prompt: System prompt (optional)
            rag_context: Retrieved context from RAG (optional)

        Returns:
            ContextWindow ready for LLM consumption
        """
        messages: list[dict] = []
        total_tokens = 0
        budget = self.config.available_for_context

        # 1. System prompt
        if system_prompt:
            system_tokens = self._estimate_tokens(system_prompt)
            messages.append({"role": "system", "content": system_prompt})
            total_tokens += system_tokens

        # 2. RAG context (as system message addendum)
        rag_chunks_used = 0
        if rag_context:
            rag_tokens = min(
                self._estimate_tokens(rag_context),
                self.config.max_rag_tokens,
            )
            if total_tokens + rag_tokens < budget:
                rag_message = f"Relevant context from codebase:\n\n{rag_context}"
                messages.append({"role": "system", "content": rag_message})
                total_tokens += rag_tokens
                rag_chunks_used = rag_context.count("---") + 1

        # 3. Check if we need a summary
        has_summary = False
        all_messages = history.get_all()
        if len(all_messages) > self.config.summarize_after:
            summary = self._get_or_create_summary(history)
            if summary:
                summary_tokens = self._estimate_tokens(summary)
                if total_tokens + summary_tokens < budget:
                    messages.append({
                        "role": "system",
                        "content": f"Summary of earlier conversation:\n{summary}",
                    })
                    total_tokens += summary_tokens
                    has_summary = True

        # 4. Recent messages (fill remaining budget)
        recent = history.get_recent(limit=self.config.recent_messages)
        included_count = 0
        truncated = False

        # Reserve space for user message
        user_tokens = self._estimate_tokens(user_message)
        remaining_budget = budget - total_tokens - user_tokens

        # Add messages from oldest to newest (of the recent set)
        messages_to_add = []
        for msg in recent:
            msg_tokens = msg.token_count or self._estimate_tokens(msg.content)
            if remaining_budget >= msg_tokens:
                messages_to_add.append({"role": msg.role, "content": msg.content})
                remaining_budget -= msg_tokens
                total_tokens += msg_tokens
                included_count += 1
            else:
                truncated = True
                break

        messages.extend(messages_to_add)

        # 5. Current user message
        messages.append({"role": "user", "content": user_message})
        total_tokens += user_tokens
        included_count += 1

        return ContextWindow(
            messages=messages,
            total_tokens=total_tokens,
            included_message_count=included_count,
            truncated=truncated,
            has_summary=has_summary,
            rag_chunks_used=rag_chunks_used,
        )

    def build_simple(
        self,
        messages: list["Message"],
        max_tokens: int | None = None,
    ) -> ContextWindow:
        """
        Build context from a list of messages (simpler interface).

        Keeps as many recent messages as fit within token budget.
        """
        budget = max_tokens or self.config.available_for_context
        result: list[dict] = []
        total_tokens = 0

        # Start from most recent
        for msg in reversed(messages):
            msg_tokens = msg.token_count or self._estimate_tokens(msg.content)

            if total_tokens + msg_tokens <= budget:
                result.insert(0, {"role": msg.role, "content": msg.content})
                total_tokens += msg_tokens
            elif msg.role == "system" and self.config.always_include_system:
                # Always include system messages
                result.insert(0, {"role": msg.role, "content": msg.content})
                total_tokens += msg_tokens
            else:
                break

        return ContextWindow(
            messages=result,
            total_tokens=total_tokens,
            included_message_count=len(result),
            truncated=len(result) < len(messages),
        )

    def should_summarize(self, history: "ConversationHistory") -> bool:
        """Check if history should be summarized."""
        return history.count() > self.config.summarize_after

    def invalidate_summary(self, session_id: str) -> None:
        """Invalidate cached summary for a session."""
        self._summary_cache.pop(session_id, None)

    def _get_or_create_summary(self, history: "ConversationHistory") -> str | None:
        """Get cached summary or create placeholder."""
        session_id = history.session.id

        if session_id in self._summary_cache:
            return self._summary_cache[session_id]

        # For now, return None - actual summarization requires LLM call
        # which should be done asynchronously
        return None

    def set_summary(self, session_id: str, summary: str) -> None:
        """Set summary for a session (called after async summarization)."""
        self._summary_cache[session_id] = summary

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Uses simple heuristic: ~4 characters per token.
        For production, use tiktoken or model-specific tokenizer.
        """
        return len(text) // 4 + 1


@dataclass
class SummarizationRequest:
    """Request to summarize messages (for async processing)."""

    session_id: str
    messages: list[dict]
    max_tokens: int = 500

    def to_prompt(self) -> str:
        """Generate summarization prompt."""
        conversation = "\n".join(
            f"{m['role']}: {m['content']}" for m in self.messages
        )
        return f"""Summarize this conversation concisely, preserving key information:

{conversation}

Summary (max {self.max_tokens} tokens):"""
