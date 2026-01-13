"""LLM client abstraction layer."""

from abc import ABC, abstractmethod
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator
import os

from openai import OpenAI, AzureOpenAI, AsyncAzureOpenAI
from dotenv import load_dotenv

# Use the same log file as handlers
_log = logging.getLogger("openagent")


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


from openagent.config import Config, LLMConfig

# ... (LLMResponse and LLMClient classes remain unchanged)

class AzureOpenAIClient(LLMClient):
    """Azure OpenAI implementation using the standard OpenAI library."""

    def __init__(
        self,
        config: LLMConfig | None = None,
    ):
        if config is None:
            full_config = Config.load()
            self.config = full_config.llm
        else:
            self.config = config

        self.endpoint = self.config.endpoint
        self.model = self.config.model
        self.api_key = self.config.api_key
        api_version = "2024-02-01"

        if not self.endpoint or not self.api_key:
            raise ValueError(
                "Azure OpenAI requires endpoint and api_key to be configured "
                "(via env vars like AZURE_OPENAI_ENDPOINT/AZURE_KEY or config file)"
            )

        self._client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=api_version,
        )

        self._async_client = AsyncAzureOpenAI(
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
        """Async completion using native async client."""
        params = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        if temperature != 1.0 and not self.model.startswith(("o1", "gpt-5")):
            params["temperature"] = temperature
        params.update(kwargs)

        response = await self._async_client.chat.completions.create(**params)

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

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Stream response chunks using native async client."""
        _log.info(f"LLM.stream: model={self.model}, messages={len(messages)}, max_tokens={max_tokens}")

        params = {
            "model": self.model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "stream": True,
        }
        if temperature != 1.0 and not self.model.startswith(("o1", "gpt-5")):
            params["temperature"] = temperature
        params.update(kwargs)

        _log.info("LLM.stream: Calling Azure OpenAI API...")
        response = await self._async_client.chat.completions.create(**params)
        _log.info("LLM.stream: Got response object, iterating chunks...")

        chunk_count = 0
        async for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                chunk_count += 1
                yield chunk.choices[0].delta.content

        _log.info(f"LLM.stream: Finished, yielded {chunk_count} chunks")
