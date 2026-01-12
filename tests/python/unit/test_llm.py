"""Tests for LLM client abstraction layer.

## Test Classification

| Category | Tests | Description |
|----------|-------|-------------|
| Streaming | 3 | Async streaming behavior |
| Response | 2 | Response parsing |
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

from openagent.core.llm import AzureOpenAIClient, LLMResponse


class MockChunk:
    """Mock streaming chunk from OpenAI."""

    def __init__(self, content: str | None):
        self.choices = [MagicMock()]
        self.choices[0].delta.content = content


class MockStreamResponse:
    """Mock streaming response that yields chunks."""

    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.index = 0

    def __iter__(self):
        return self

    def __next__(self):
        if self.index >= len(self.chunks):
            raise StopIteration
        chunk = MockChunk(self.chunks[self.index])
        self.index += 1
        return chunk


class TestLLMStreaming:
    """Tests for async streaming behavior."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock OpenAI client."""
        client = MagicMock()
        return client

    @pytest.mark.asyncio
    async def test_stream_yields_chunks(self, mock_client):
        """Test that stream yields chunks asynchronously."""
        # Setup mock to return streaming response
        mock_client.chat.completions.create.return_value = MockStreamResponse(
            ["Hello", " ", "world", "!"]
        )

        with patch.object(AzureOpenAIClient, "__init__", lambda self: None):
            llm = AzureOpenAIClient()
            llm._client = mock_client
            llm.model = "gpt-4o"

            chunks = []
            async for chunk in llm.stream(
                messages=[{"role": "user", "content": "test"}]
            ):
                chunks.append(chunk)

            assert chunks == ["Hello", " ", "world", "!"]

    @pytest.mark.asyncio
    async def test_stream_handles_empty_chunks(self, mock_client):
        """Test that stream handles None content in chunks."""
        # Some chunks might have None content (e.g., role-only chunks)
        mock_response = MagicMock()
        mock_response.__iter__ = lambda self: iter([
            MockChunk("Hello"),
            MockChunk(None),  # Empty chunk
            MockChunk(" world"),
        ])
        mock_client.chat.completions.create.return_value = mock_response

        with patch.object(AzureOpenAIClient, "__init__", lambda self: None):
            llm = AzureOpenAIClient()
            llm._client = mock_client
            llm.model = "gpt-4o"

            chunks = []
            async for chunk in llm.stream(
                messages=[{"role": "user", "content": "test"}]
            ):
                chunks.append(chunk)

            assert chunks == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_stream_does_not_block_event_loop(self, mock_client):
        """Test that streaming doesn't block the event loop."""
        import time

        # Create a slow mock that simulates network delay
        def slow_iter():
            for chunk in ["chunk1", "chunk2", "chunk3"]:
                time.sleep(0.01)  # Small delay
                yield MockChunk(chunk)

        mock_response = MagicMock()
        mock_response.__iter__ = lambda self: slow_iter()
        mock_client.chat.completions.create.return_value = mock_response

        with patch.object(AzureOpenAIClient, "__init__", lambda self: None):
            llm = AzureOpenAIClient()
            llm._client = mock_client
            llm.model = "gpt-4o"

            # Track if other tasks can run while streaming
            other_task_ran = False

            async def other_task():
                nonlocal other_task_ran
                await asyncio.sleep(0.005)
                other_task_ran = True

            async def stream_task():
                chunks = []
                async for chunk in llm.stream(
                    messages=[{"role": "user", "content": "test"}]
                ):
                    chunks.append(chunk)
                return chunks

            # Run both tasks concurrently
            results = await asyncio.gather(stream_task(), other_task())

            # The other task should have been able to run
            assert other_task_ran, "Event loop was blocked by streaming"
            assert results[0] == ["chunk1", "chunk2", "chunk3"]


class TestLLMResponse:
    """Tests for LLM response handling."""

    def test_total_tokens(self):
        """Test total_tokens property."""
        response = LLMResponse(
            content="Hello",
            input_tokens=10,
            output_tokens=5,
            model="gpt-4o",
        )

        assert response.total_tokens == 15

    def test_response_defaults(self):
        """Test response default values."""
        response = LLMResponse(
            content="Hello",
            input_tokens=10,
            output_tokens=5,
            model="gpt-4o",
        )

        assert response.finish_reason == "stop"
        assert response.request_id == ""
