# OpenAgent

**A token-efficient AI assistant for navigating large codebases**

OpenAgent combines the power of semantic code search with intelligent LLM routing to help you understand, explore, and work with complex projects. Built with a sleek Rust TUI frontend and a Python backend featuring Azure OpenAI, ChromaDB vector storage, and DSPy-powered intent classification.

## What is OpenAgent?

OpenAgent is designed to solve a fundamental challenge in AI-assisted development: efficiently understanding large codebases without blowing through token budgets. It achieves this through:

- **Semantic Code Search**: ChromaDB-powered RAG (Retrieval-Augmented Generation) finds relevant code across your entire project
- **Smart Intent Routing**: DSPy classifies queries (RESEARCH, ORGANIZE, CONTROL) to optimize response strategies
- **Token Tracking**: Real-time monitoring and cost estimation keeps usage under control
- **Persistent Sessions**: SQLite-backed conversation history that survives restarts
- **Modern TUI**: Responsive terminal interface built with Rust and Ratatui

## Features

- **Code-Aware RAG**: Vector embeddings tuned for code semantics, not just text similarity
- **Intelligent Context Building**: Smart context window management prioritizes the most relevant code
- **Two-Process Architecture**: Rust TUI communicates with Python backend via JSON-RPC for optimal performance
- **Extensible Tool System**: Built-in filesystem, git, and shell tool execution
- **Azure OpenAI Integration**: Leverages high-capacity models with robust error handling
- **MCP Support**: Model Context Protocol host for standardized tool integration

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Rust** (latest stable)
- **Azure OpenAI** credentials with API access

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/apramodk/OpenAgent.git
   cd OpenAgent
   ```

2. **Set up your environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Azure OpenAI credentials:
   # AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   # AZURE_OPENAI_API_KEY=your-api-key
   # AZURE_OPENAI_DEPLOYMENT=your-deployment-name
   ```

3. **Run the automated setup**
   ```bash
   ./setup.sh
   ```
   This creates a virtual environment, installs all Python dependencies, and builds the Rust TUI.

4. **Start OpenAgent**
   ```bash
   ./run.sh
   ```

That's it! OpenAgent will launch with the TUI connected to the Python backend.

## Usage

### Running OpenAgent

```bash
./run.sh              # Normal mode: TUI + backend
./run.sh --offline    # Offline mode: TUI only (for testing UI)
./run.sh --rebuild    # Rebuild TUI before launching
```

### TUI Commands

Once inside the TUI, use these slash commands:

| Command | Description |
|---------|-------------|
| `/help` | Show available commands |
| `/init` | Index the current codebase for semantic search |
| `/rag` | Check RAG indexing status |
| `/clear` | Clear chat history |
| `/quit` or `/exit` | Exit the application |

### Indexing Your Codebase

Before asking code-specific questions, index your project:

```
/init
```

OpenAgent will scan your codebase, create embeddings, and store them in ChromaDB for fast semantic retrieval.

## Architecture

### Two-Process Model

```
┌─────────────┐   JSON-RPC over stdio   ┌──────────────────┐
│  Rust TUI   │ <───────────────────────> │ Python Backend   │
│  (ratatui)  │                           │ (Agent + RAG)    │
└─────────────┘                           └──────────────────┘
```

- **Rust TUI**: Handles rendering, user input, and display logic
- **Python Backend**: Runs the agent, LLM calls, RAG queries, and tool execution

### Project Structure

```
OpenAgent/
├── openagent/              # Python backend
│   ├── core/              # Agent, LLM, and intent routing
│   ├── memory/            # Session, conversation, context management
│   ├── rag/               # ChromaDB vector store and code scanner
│   ├── tools/             # MCP host and tool executor
│   ├── server/            # JSON-RPC server
│   └── telemetry/         # Token tracking and cost estimation
├── TUI/                   # Rust frontend
│   └── src/
│       ├── main.rs        # Entry point and event loop
│       ├── app.rs         # Application state
│       ├── ui.rs          # UI rendering
│       ├── markdown.rs    # Chat output rendering
│       └── backend.rs     # JSON-RPC client
├── tests/                 # Python test suite
├── scripts/               # Utility scripts
├── setup.sh               # One-command setup
└── run.sh                 # Launch script
```

## Development

### Running Tests

```bash
pytest tests/                          # Run all tests
pytest tests/ -m "not slow"           # Skip slow tests
pytest tests/python/unit/test_foo.py  # Run specific test file
pytest --cov=openagent tests/         # With coverage report
```

### Code Quality

```bash
black openagent/                      # Format Python code
ruff check openagent/ --fix           # Lint with auto-fix
mypy openagent/                       # Type checking
```

### Building the TUI

```bash
cd TUI
cargo build --release                 # Production build
cargo test                            # Run Rust tests
cargo run                             # Development run
```

### Manual Backend Usage

You can run the Python backend standalone:

```bash
python -m openagent              # Interactive CLI mode
python -m openagent server       # JSON-RPC server mode (for TUI)
```

## Configuration

OpenAgent uses `pyproject.toml` for Python dependencies and build configuration. Environment variables are loaded from `.env`:

```bash
# Required
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT=your-deployment-name

# Optional
AZURE_OPENAI_API_VERSION=2024-02-15-preview
CHROMA_PERSIST_DIR=.chromadb
```

## Key Modules

| Module | Purpose |
|--------|---------|
| `core/agent.py` | Main orchestrator with sync/async chat, RAG integration |
| `core/llm.py` | Azure OpenAI client with retry logic and error handling |
| `core/intent.py` | DSPy-based intent classification (RESEARCH/ORGANIZE/CONTROL) |
| `memory/session.py` | SQLite session persistence |
| `memory/conversation.py` | Message history with token tracking |
| `memory/context.py` | Smart context window building and optimization |
| `rag/store.py` | ChromaDB vector store for semantic code search |
| `tools/executor.py` | Tool execution loop with safety checks |
| `server/jsonrpc.py` | JSON-RPC 2.0 server implementation |

## Contributing

Contributions are welcome! Please ensure:

1. Tests pass: `pytest tests/`
2. Code is formatted: `black openagent/`
3. Linting passes: `ruff check openagent/`
4. Type checking passes: `mypy openagent/`

## License

MIT License - see LICENSE file for details

## Acknowledgments

Built with:
- [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) for LLM capabilities
- [ChromaDB](https://www.trychroma.com/) for vector storage
- [DSPy](https://github.com/stanfordnlp/dspy) for intent classification
- [Ratatui](https://ratatui.rs/) for the terminal UI
- [Crossterm](https://github.com/crossterm-rs/crossterm) for terminal control
