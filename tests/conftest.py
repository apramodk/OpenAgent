"""Shared pytest fixtures."""

import pytest
from pathlib import Path
import tempfile
import shutil


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
