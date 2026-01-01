"""LLM client abstraction layer."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator
import os

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from dotenv import load_dotenv


@dataclass
class LLMResponse:
    """Response from an LLM call."""

    content: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str = "stop"
    request_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Send messages and get complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream response chunks."""
        ...

    @abstractmethod
    def complete_sync(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Synchronous version of complete."""
        ...


class AzureOpenAIClient(LLMClient):
    """Azure OpenAI implementation using AIProjectClient."""

    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        credential: DefaultAzureCredential | None = None,
    ):
        load_dotenv()

        self.endpoint = endpoint or os.environ.get("PROJECT_ENDPOINT", "")
        self.model = model or os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
        self.credential = credential or DefaultAzureCredential()

        self._project_client = AIProjectClient(
            endpoint=self.endpoint,
            credential=self.credential,
        )
        self._client = self._project_client.get_openai_client()

    def complete_sync(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Synchronous completion."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs,
        )

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            content=choice.message.content or "",
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            model=response.model,
            finish_reason=choice.finish_reason or "stop",
            request_id=response.id,
        )

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Async completion - wraps sync for now."""
        # TODO: Use async client when available
        return self.complete_sync(messages, max_tokens, temperature, **kwargs)

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream response chunks."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
            **kwargs,
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
