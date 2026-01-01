"""LLM client abstraction layer."""

from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import AsyncIterator
import os

from openai import OpenAI, AzureOpenAI
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
    """Azure OpenAI implementation using the standard OpenAI library."""

    def __init__(
        self,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        api_version: str = "2024-02-01",
    ):
        load_dotenv()

        # Azure endpoint should be like: https://resource.openai.azure.com/
        # Use env var if not provided or empty
        self.endpoint = endpoint if endpoint else os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        if not self.endpoint:
            # Try to extract from PROJECT_ENDPOINT_OAI
            oai_endpoint = os.environ.get("PROJECT_ENDPOINT_OAI", "")
            if oai_endpoint:
                # Extract base URL from full endpoint
                # https://x.cognitiveservices.azure.com/openai/deployments/...
                parts = oai_endpoint.split("/openai/")
                if parts:
                    self.endpoint = parts[0]

        # Use env var if not provided or empty
        self.model = model if model else os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
        self.api_key = api_key if api_key else os.environ.get("AZURE_KEY", "")

        if not self.endpoint or not self.api_key:
            raise ValueError(
                "Azure OpenAI requires AZURE_OPENAI_ENDPOINT (or PROJECT_ENDPOINT_OAI) "
                "and AZURE_KEY environment variables"
            )

        self._client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=api_version,
        )

    def complete_sync(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        """Synchronous completion."""
        # Build request params - some models (o1, gpt-5) don't support temperature
        params = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        # Only add temperature if not default (some models reject it)
        if temperature != 1.0 and not self.model.startswith(("o1", "gpt-5")):
            params["temperature"] = temperature
        params.update(kwargs)

        response = self._client.chat.completions.create(**params)

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
        params = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "stream": True,
        }
        if temperature != 1.0 and not self.model.startswith(("o1", "gpt-5")):
            params["temperature"] = temperature
        params.update(kwargs)

        # Use a queue to bridge sync iteration to async
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        def _sync_stream():
            """Run sync streaming in thread and put chunks in queue."""
            try:
                response = self._client.chat.completions.create(**params)
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        # Put chunk in queue (blocks if queue is full, but that's ok in thread)
                        asyncio.run_coroutine_threadsafe(
                            queue.put(chunk.choices[0].delta.content),
                            loop
                        ).result()
            finally:
                # Signal end of stream
                asyncio.run_coroutine_threadsafe(queue.put(None), loop).result()

        loop = asyncio.get_event_loop()
        # Run sync streaming in background thread
        asyncio.get_event_loop().run_in_executor(None, _sync_stream)

        # Yield chunks as they arrive
        while True:
            chunk = await queue.get()
            if chunk is None:
                break
            yield chunk
