# OpenAgent Roadmap

## Vision
A token-efficient AI assistant for navigating large codebases. Pre-generates semantic specs, stores in vector DB, queries only relevant context per request.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Rust TUI (ratatui)                       │
│ ┌───────────────┐                                           │
│ │ Tokens: 1.2k  │  (token monitor - top left)               │
│ │ ████░░ $0.02  │                                           │
│ └───────────────┘                                           │
│  ┌─────────────┐  ┌─────────────────────────────────────┐   │
│  │ File Tree   │  │          Chat/Output Pane           │   │
│  │             │  │                                     │   │
│  │ > src/      │  │  user: How does auth work?          │   │
│  │   agent.py  │  │  assistant: The auth module...      │   │
│  │   main.py   │  │                                     │   │
│  │             │  ├─────────────────────────────────────┤   │
│  │             │  │          Input Bar                  │   │
│  └─────────────┘  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ IPC (JSON-RPC or stdio)
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python AI Core                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Intent       │  │ RAG          │  │ Conversation     │   │
│  │ Router       │  │ (ChromaDB)   │  │ Memory           │   │
│  │ (DSPy)       │  │              │  │                  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ MCP Host     │  │ Tool         │  │ LLM Client       │   │
│  │              │  │ Executor     │  │ (Azure)          │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Token Tracker (input/output/total, cost estimation) │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCP Servers (Tools)                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ filesystem   │  │ git          │  │ codebase         │   │
│  │ read/write   │  │ operations   │  │ search           │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Testing Philosophy

**Every component must have tests.** Testing is not optional.

### Testing Stack
- **Python**: pytest + pytest-asyncio + pytest-cov
- **Rust**: Built-in test framework + cargo-tarpaulin (coverage)
- **Integration**: End-to-end tests via subprocess

### Testing Requirements
| Component Type | Required Tests |
|----------------|----------------|
| Core logic | Unit tests (90%+ coverage) |
| LLM interactions | Mock-based unit tests + integration tests with real API |
| IPC protocol | Serialization/deserialization tests |
| RAG queries | Unit tests with fixture data |
| MCP servers | Unit tests + integration tests |
| TUI | Widget unit tests + snapshot tests |
| CLI commands | End-to-end tests |

### Test Directory Structure
```
tests/
├── python/
│   ├── unit/
│   │   ├── test_intent.py
│   │   ├── test_memory.py
│   │   ├── test_rag.py
│   │   └── test_tools.py
│   ├── integration/
│   │   ├── test_llm_client.py
│   │   └── test_mcp_host.py
│   └── fixtures/
│       ├── sample_codebase/
│       └── mock_responses.json
└── rust/
    └── (inline in src/ files + integration tests)
```

---

## Token Usage Monitoring

### Token Monitor Component
Located in top-left corner of TUI. Always visible.

**Display**:
```
┌─────────────────┐
│ Session: 2.4k   │  ← total tokens this session
│ ████████░░ 24%  │  ← visual bar (% of budget if set)
│ ~$0.04          │  ← estimated cost
└─────────────────┘
```

**Features**:
- Real-time updates as responses stream
- Input vs output token breakdown (hover/expand)
- Cost estimation based on model pricing
- Session budget warnings (configurable)
- Historical usage per session (stored in DB)

**Data Tracked**:
```python
@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    model: str
    timestamp: datetime
    request_id: str

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def estimated_cost(self) -> float:
        # Model-specific pricing
        ...
```

**IPC Events**:
```json
{
    "jsonrpc": "2.0",
    "method": "token_update",
    "params": {
        "session_total": 2400,
        "last_request": {
            "input": 150,
            "output": 320
        },
        "estimated_cost_usd": 0.04
    }
}
```

---

## Phase 1: Foundation (Current → Stable Core)

### 1.1 Python Core Refactor
**Goal**: Clean, modular Python backend that can be driven by any frontend.

**Tasks**:
- [ ] Restructure into proper package layout
- [ ] Create `openagent/` package with submodules
- [ ] Define clear interfaces between components
- [ ] Add proper error handling and logging
- [ ] Set up pytest with coverage reporting
- [ ] Add pre-commit hooks (black, ruff, mypy)

**Target Structure**:
```
openagent/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── agent.py          # Main orchestrator
│   ├── intent.py         # DSPy intent router
│   └── llm.py            # LLM client abstraction
├── memory/
│   ├── __init__.py
│   ├── conversation.py   # Conversation history
│   └── session.py        # Session persistence
├── rag/
│   ├── __init__.py
│   ├── store.py          # ChromaDB wrapper
│   └── query.py          # Semantic search
├── tools/
│   ├── __init__.py
│   ├── executor.py       # Tool execution
│   └── registry.py       # Tool discovery
├── telemetry/
│   ├── __init__.py
│   └── tokens.py         # Token tracking
└── server/
    ├── __init__.py
    └── jsonrpc.py        # IPC server for Rust TUI
```

**Tests Required**:
- [ ] `test_agent.py`: Agent initialization, message flow
- [ ] `test_intent.py`: Intent extraction, action classification
- [ ] `test_llm.py`: Client abstraction, error handling
- [ ] `test_tokens.py`: Token counting, cost calculation

### 1.2 IPC Protocol Design
**Goal**: Define how Rust TUI communicates with Python backend.

**Protocol**: JSON-RPC 2.0 over stdio
- TUI spawns Python process
- Communication via stdin/stdout
- Structured request/response format

**Methods**:
```
# Core
chat.send           - Send message, get response
chat.cancel         - Cancel in-progress request

# Session
session.create      - Create new session
session.load        - Load existing session
session.list        - List all sessions

# Telemetry
tokens.get          - Get current token usage
tokens.subscribe    - Subscribe to token updates

# Tools
tools.list          - List available tools
tools.call          - Directly call a tool
```

**Tests Required**:
- [ ] `test_jsonrpc.py`: Request/response serialization, error handling
- [ ] `test_protocol.py`: Full request-response cycles with mocks

---

## Phase 2: Conversation Memory

### 2.1 Session Management
**Goal**: Persist conversations across sessions.

**Components**:
- Session ID generation and management
- SQLite backend for conversation storage
- Automatic context windowing (keep recent + important)

**Schema**:
```sql
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP,
    last_accessed TIMESTAMP,
    codebase_path TEXT,
    metadata JSON
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    role TEXT,  -- user, assistant, system, tool
    content TEXT,
    timestamp TIMESTAMP,
    token_count INTEGER,
    metadata JSON
);

CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    message_id INTEGER REFERENCES messages(id),
    input_tokens INTEGER,
    output_tokens INTEGER,
    model TEXT,
    timestamp TIMESTAMP
);

CREATE TABLE context_refs (
    id INTEGER PRIMARY KEY,
    message_id INTEGER REFERENCES messages(id),
    chunk_id TEXT,  -- reference to RAG chunk
    relevance_score FLOAT
);
```

**Tests Required**:
- [ ] `test_session.py`: CRUD operations, session lifecycle
- [ ] `test_conversation.py`: Message storage, retrieval, ordering
- [ ] `test_token_storage.py`: Token usage persistence, aggregation

### 2.2 Context Management
**Goal**: Smart context selection to minimize tokens.

**Strategy**:
1. Keep last N messages (sliding window)
2. Summarize older context periodically
3. Pull relevant RAG chunks per query
4. Track which chunks were useful (feedback loop)

**Tests Required**:
- [ ] `test_context_window.py`: Sliding window logic
- [ ] `test_summarization.py`: Context compression
- [ ] `test_chunk_selection.py`: RAG integration

---

## Phase 3: MCP Integration

### 3.1 MCP Host Implementation
**Goal**: Python can call MCP-compliant tool servers.

**Components**:
- MCP client library integration
- Tool discovery and capability negotiation
- Request/response handling
- Error handling and retries

**Tests Required**:
- [ ] `test_mcp_client.py`: Protocol compliance, connection handling
- [ ] `test_tool_discovery.py`: Capability parsing
- [ ] `test_mcp_errors.py`: Error handling, retries

### 3.2 Built-in MCP Servers
**Goal**: Essential tools as MCP servers.

**Servers to Build**:
1. **filesystem**: Read, write, list, search files
2. **git**: Status, diff, log, blame
3. **codebase**: Semantic search via RAG
4. **shell**: Execute commands (sandboxed)

**Tests Required** (per server):
- [ ] Unit tests for each tool function
- [ ] Integration tests with real filesystem/git
- [ ] Security tests (sandboxing, path traversal prevention)

### 3.3 Tool Execution Loop
**Goal**: Agent can decide to use tools and act on results.

**Flow**:
```
User Query
    ↓
Intent Router (research/organize/control)
    ↓
┌─────────────────────────────┐
│   Tool Selection            │
│   (which tools are needed?) │
└─────────────────────────────┘
    ↓
┌─────────────────────────────┐
│   Tool Execution            │  ←──┐
│   (call MCP servers)        │     │
└─────────────────────────────┘     │
    ↓                               │
┌─────────────────────────────┐     │
│   Result Processing         │     │
│   (need more tools?)        │ ────┘
└─────────────────────────────┘
    ↓
Response to User
```

**Tests Required**:
- [ ] `test_tool_selection.py`: Correct tool chosen for intent
- [ ] `test_execution_loop.py`: Multi-step tool chains
- [ ] `test_loop_termination.py`: Prevent infinite loops

---

## Phase 4: Rust TUI

### 4.1 Core TUI Framework
**Goal**: Interactive terminal interface like Claude Code.

**Layout**:
```
┌───────────────┬─────────────────────────────────────────────┐
│ Token Monitor │                                             │
│ ┌───────────┐ │                                             │
│ │ 2.4k tkns │ │                                             │
│ │ ████░░    │ │         Chat Pane                           │
│ │ $0.04     │ │                                             │
│ └───────────┘ │                                             │
├───────────────┤                                             │
│               │                                             │
│  File Tree    │                                             │
│  (toggleable) │                                             │
│               ├─────────────────────────────────────────────┤
│               │  > Input bar                                │
└───────────────┴─────────────────────────────────────────────┘
```

**Key Features**:
- Vim-style keybindings
- Markdown rendering in terminal
- Syntax highlighting for code blocks
- Copy/paste support

**Tests Required**:
- [ ] Widget unit tests (token monitor, chat pane, input bar)
- [ ] Layout tests (resize handling)
- [ ] Keybinding tests
- [ ] Snapshot tests for UI states

### 4.2 Python Process Management
**Goal**: TUI manages Python backend lifecycle.

**Responsibilities**:
- Spawn Python process on startup
- Handle process crashes gracefully
- Stream responses in real-time
- Queue requests during processing

**Tests Required**:
- [ ] `test_process_spawn.rs`: Process lifecycle
- [ ] `test_stream_parsing.rs`: JSON-RPC stream handling
- [ ] `test_crash_recovery.rs`: Graceful degradation

### 4.3 Token Monitor Widget
**Goal**: Real-time token usage display.

**Implementation**:
```rust
struct TokenMonitor {
    session_total: u64,
    last_input: u64,
    last_output: u64,
    budget: Option<u64>,
    cost_usd: f64,
}

impl Widget for TokenMonitor {
    fn render(self, area: Rect, buf: &mut Buffer) {
        // Render token count
        // Render progress bar
        // Render cost estimate
    }
}
```

**Tests Required**:
- [ ] `test_token_monitor.rs`: Rendering, updates, budget warnings

### 4.4 UI Polish
**Goal**: Smooth, responsive experience.

**Features**:
- Loading indicators
- Error display
- Session switching
- Configuration (keybinds, colors, model)

---

## Phase 5: Codebase Ingestion

### 5.1 File Scanner
**Goal**: Automatically discover and parse code files.

**Features**:
- Respect .gitignore
- Language detection
- Incremental updates (only changed files)
- Progress reporting

**Tests Required**:
- [ ] `test_scanner.py`: File discovery, ignore patterns
- [ ] `test_language_detection.py`: Correct language identification
- [ ] `test_incremental.py`: Change detection

### 5.2 Semantic Extraction
**Goal**: Generate specs for all code files.

**Pipeline**:
```
File → Parse → Chunk → LLM Extract → Store in ChromaDB
```

**Tests Required**:
- [ ] `test_chunking.py`: Correct chunk boundaries
- [ ] `test_extraction.py`: Semantic extraction quality (with fixtures)
- [ ] `test_storage.py`: ChromaDB integration

### 5.3 Index Management
**Goal**: Keep specs up to date.

**Tests Required**:
- [ ] `test_watch.py`: File change detection
- [ ] `test_reindex.py`: Incremental updates
- [ ] `test_multi_codebase.py`: Multiple codebase handling

---

## Phase 6: Advanced Features

### 6.1 Multi-Codebase Support
- Switch between indexed codebases
- Cross-codebase queries
- Codebase-specific sessions

### 6.2 Personal Knowledge Graph
- Store user's mental model
- Learn from interactions
- Proactive suggestions

### 6.3 RAG-Based Tool Discovery
- Tools described in RAG
- Dynamic tool selection
- Scale to many tools without context bloat

---

## Development Setup

### Prerequisites
```bash
# Python
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Rust
cd TUI
cargo build
```

### Running Tests
```bash
# Python
pytest --cov=openagent --cov-report=html

# Rust
cd TUI
cargo test
cargo tarpaulin  # coverage
```

### Pre-commit Hooks
```bash
pip install pre-commit
pre-commit install
```

---

## Priority Order

| Phase | Priority | Effort | Dependencies |
|-------|----------|--------|--------------|
| 1.1 Python Refactor | HIGH | Medium | None |
| 1.2 IPC Protocol | HIGH | Low | None |
| 2.1 Session Management | HIGH | Medium | 1.1 |
| 2.2 Context Management | HIGH | Medium | 2.1 |
| 3.1 MCP Host | HIGH | Medium | 1.1 |
| 3.2 Built-in MCP Servers | MEDIUM | High | 3.1 |
| 3.3 Tool Execution Loop | HIGH | Medium | 3.1 |
| 4.1 Core TUI | HIGH | High | 1.2 |
| 4.2 Process Management | HIGH | Medium | 4.1 |
| 4.3 Token Monitor | HIGH | Low | 4.1 |
| 4.4 UI Polish | LOW | Medium | 4.2 |
| 5.x Ingestion | MEDIUM | High | 1.1 |
| 6.x Advanced | LOW | High | All above |

---

## Immediate Next Steps

1. **Refactor Python into package structure** (Phase 1.1)
   - Set up pytest, coverage, pre-commit
   - Create module structure
   - Write initial tests

2. **Implement JSON-RPC server** (Phase 1.2)
   - Define protocol schema
   - Implement server
   - Write protocol tests

3. **Build token tracking** (Phase 1.1 addon)
   - Token counter class
   - Cost estimation
   - Storage schema

4. **Build conversation memory** (Phase 2.1)
   - SQLite schema
   - Session management
   - Message persistence

5. **Implement MCP host** (Phase 3.1)
   - Client implementation
   - Tool discovery
   - Integration tests

6. **Build Rust TUI shell** (Phase 4.1)
   - Basic layout
   - Token monitor widget
   - Python process management

Each step builds on the previous, creating a functional system at each milestone.
