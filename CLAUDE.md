# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OpenAgent is a token-efficient AI assistant for navigating large codebases. It uses a Rust TUI frontend communicating via JSON-RPC with a Python backend that integrates Azure OpenAI, ChromaDB for semantic search, and DSPy for intent routing.

## Build & Development Commands

### Initial Setup
```bash
./setup.sh  # Creates venv, installs Python deps, builds Rust TUI
```

### Running
```bash
./run.sh              # Run TUI with backend
./run.sh --offline    # Run TUI without backend (testing UI)
./run.sh --rebuild    # Rebuild TUI before running
```

### Testing
```bash
pytest tests/                          # Run all tests
pytest tests/ -m "not slow"           # Skip slow tests
pytest tests/python/unit/test_foo.py  # Run single test file
pytest --cov=openagent tests/         # With coverage
```

### Linting & Formatting
```bash
black openagent/                      # Format Python
ruff check openagent/ --fix           # Lint with auto-fix
mypy openagent/                       # Type checking
```

### Rust TUI (in TUI/ directory)
```bash
cargo build --release                 # Build TUI
cargo test                            # Run Rust tests
```

## Architecture

### Two-Process Model
- **Rust TUI** (`TUI/src/`): Terminal interface using ratatui + crossterm
- **Python Backend** (`openagent/`): Core logic, runs as JSON-RPC server over stdio

Communication flows: `TUI <--JSON-RPC--> Python Server`

### Python Backend Modules

| Module | Purpose |
|--------|---------|
| `core/agent.py` | Main orchestrator with sync/async chat, RAG integration |
| `core/llm.py` | Azure OpenAI client abstraction |
| `core/intent.py` | DSPy-based intent extraction (research/organize/control) |
| `memory/session.py` | SQLite session persistence |
| `memory/conversation.py` | Message history with token tracking |
| `memory/context.py` | Smart context window building |
| `rag/store.py` | ChromaDB vector store for semantic code search |
| `tools/mcp.py` | MCP (Model Context Protocol) host |
| `tools/executor.py` | Tool execution loop |
| `server/jsonrpc.py` | JSON-RPC 2.0 server |
| `telemetry/tokens.py` | Token counting and cost estimation |
| `config.py` | Dataclass configuration with TOML + env overrides |

### Rust TUI Structure

| File | Purpose |
|------|---------|
| `main.rs` | Entry point, terminal setup, event loop |
| `app.rs` | Application state management |
| `ui.rs` | UI rendering (file tree, chat pane, input bar) |
| `markdown.rs` | Markdown rendering for chat output |
| `backend.rs` | JSON-RPC communication with Python |

### Entry Points
- **CLI Mode**: `openagent.__main__.run_cli()` - Interactive CLI without TUI
- **Server Mode**: `openagent.__main__.run_server()` - JSON-RPC server for TUI
- **Factory**: `openagent.core.agent.create_agent()` - Creates configured agent

## Key Patterns

### Token Efficiency
The core design goal is token efficiency. The context manager (`memory/context.py`) carefully builds context windows, and token tracking (`telemetry/tokens.py`) monitors usage with cost estimation.

### Intent Routing
DSPy classifies user intents into RESEARCH, ORGANIZE, or CONTROL categories before processing, enabling optimized handling paths.

### RAG Pipeline
ChromaDB stores code embeddings for semantic search. The scanner (`rag/scanner.py`) ingests codebases, and queries retrieve relevant context before LLM calls.

## Configuration

- Environment: `.env` file (see `.env.example` for Azure OpenAI setup)
- Python: `pyproject.toml` (deps, pytest, black, ruff, mypy settings)
- Rust: `TUI/Cargo.toml`

## Database Schema (SQLite)

Sessions, messages, and token usage are persisted with schema in `memory/session.py`.
