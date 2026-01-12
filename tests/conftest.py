"""Shared pytest fixtures."""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import MagicMock, AsyncMock

from openagent.core.llm import LLMClient, LLMResponse


class MockLLMClient(LLMClient):
    """Mock LLM Client for testing without API calls."""

    def __init__(self, response_content="Mock response"):
        self.response_content = response_content
        self.complete_sync_mock = MagicMock()
        self.complete_mock = AsyncMock()
        self.stream_mock = MagicMock()

    def complete_sync(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        self.complete_sync_mock(messages, max_tokens, temperature, **kwargs)
        return LLMResponse(
            content=self.response_content,
            input_tokens=10,
            output_tokens=5,
            model="mock-model",
        )

    async def complete(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ) -> LLMResponse:
        await self.complete_mock(messages, max_tokens, temperature, **kwargs)
        return LLMResponse(
            content=self.response_content,
            input_tokens=10,
            output_tokens=5,
            model="mock-model",
        )

    async def stream(
        self,
        messages: list[dict],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        **kwargs,
    ):
        self.stream_mock(messages, max_tokens, temperature, **kwargs)
        words = self.response_content.split()
        for word in words:
            yield word + " "


@pytest.fixture
def mock_llm_client():
    """Provide a mock LLM client."""
    return MockLLMClient()


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def tmp_chroma_path(tmp_path: Path) -> Path:
    """Provide a temporary ChromaDB path."""
    chroma_path = tmp_path / "chroma"
    chroma_path.mkdir()
    return chroma_path


@pytest.fixture
def sample_messages() -> list[dict]:
    """Sample conversation messages."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you?"},
    ]


@pytest.fixture
def sample_code_chunks() -> list[dict]:
    """Sample code chunks for RAG testing."""
    return [
        {
            "id": "file_main_py",
            "content": "Main entry point for the application. Handles CLI arguments and starts the agent.",
            "metadata": {
                "path": "main.py",
                "language": "python",
                "type": "file",
                "concepts": ["cli", "entry point", "agent"],
            },
        },
        {
            "id": "func_agent_init",
            "content": "Initializes the agent with LLM client and conversation history.",
            "metadata": {
                "path": "agent.py",
                "type": "function",
                "signature": "def __init__(self, instructions: str)",
                "calls": ["load_dotenv", "AIProjectClient"],
                "called_by": ["main"],
            },
        },
        {
            "id": "func_agent_message",
            "content": "Sends a message to the LLM and returns the response.",
            "metadata": {
                "path": "agent.py",
                "type": "function",
                "signature": "def message(self, file: str) -> str",
                "calls": ["open", "llm.responses.create"],
                "called_by": ["main"],
            },
        },
    ]
