# OpenAgent Technical Specifications

## 1. Python Core Package

### 1.1 Package Structure

```
openagent/
├── __init__.py              # Version, public exports
├── core/
│   ├── __init__.py
│   ├── agent.py             # Main orchestrator
│   ├── intent.py            # DSPy intent router
│   └── llm.py               # LLM client abstraction
├── memory/
│   ├── __init__.py
│   ├── conversation.py      # Message history management
│   ├── session.py           # Session persistence (SQLite)
│   └── context.py           # Context window management
├── rag/
│   ├── __init__.py
│   ├── store.py             # ChromaDB wrapper
│   ├── query.py             # Semantic search
│   └── ingest.py            # Codebase ingestion
├── tools/
│   ├── __init__.py
│   ├── mcp_host.py          # MCP client implementation
│   ├── executor.py          # Tool execution loop
│   └── registry.py          # Tool discovery/registration
├── telemetry/
│   ├── __init__.py
│   └── tokens.py            # Token tracking and cost estimation
├── server/
│   ├── __init__.py
│   └── jsonrpc.py           # JSON-RPC server for TUI
└── config.py                # Configuration management
```

### 1.2 Core Interfaces

```python
# openagent/core/agent.py

from dataclasses import dataclass
from typing import AsyncIterator
from openagent.memory import Session, ConversationHistory
from openagent.tools import ToolExecutor
from openagent.telemetry import TokenTracker

@dataclass
class AgentConfig:
    model: str
    api_endpoint: str
    max_tokens: int = 4096
    temperature: float = 0.7
    token_budget: int | None = None

class Agent:
    """Main orchestrator that coordinates all components."""

    def __init__(
        self,
        config: AgentConfig,
        session: Session,
        tool_executor: ToolExecutor,
        token_tracker: TokenTracker,
    ):
        self.config = config
        self.session = session
        self.history = ConversationHistory(session)
        self.tools = tool_executor
        self.tokens = token_tracker
        self.intent_router = IntentRouter()

    async def chat(self, message: str) -> AsyncIterator[str]:
        """
        Process user message and stream response.

        Yields chunks of the response as they arrive.
        Updates token tracker after completion.
        """
        ...

    async def chat_with_tools(self, message: str) -> AsyncIterator[str]:
        """
        Process message with tool execution loop.

        1. Route intent
        2. Select tools if needed
        3. Execute tools
        4. Generate response
        5. Repeat if more tools needed
        """
        ...
```

```python
# openagent/core/intent.py

from dataclasses import dataclass
from enum import Enum
import dspy

class IntentType(Enum):
    RESEARCH = "research"    # Query RAG/search to learn
    ORGANIZE = "organize"    # Structure ideas
    CONTROL = "control"      # Execute actions

@dataclass
class Intent:
    type: IntentType
    entities: list[str]
    action: str              # search, clarify, answer, execute
    query: str               # Reformulated query for RAG
    confidence: float

class ExtractIntent(dspy.Signature):
    """Extract user intent from message."""

    user_input: str = dspy.InputField()
    context: str = dspy.InputField(default="")

    intent_type: str = dspy.OutputField()
    entities: list[str] = dspy.OutputField()
    action: str = dspy.OutputField()
    query: str = dspy.OutputField()

class IntentRouter:
    """Routes user messages to appropriate handlers."""

    def __init__(self):
        self.extractor = dspy.ChainOfThought(ExtractIntent)

    def route(self, message: str, context: str = "") -> Intent:
        """Extract intent from user message."""
        ...
```

```python
# openagent/core/llm.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    finish_reason: str

class LLMClient(ABC):
    """Abstract LLM client interface."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        **kwargs
    ) -> LLMResponse:
        """Send messages and get complete response."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream response chunks."""
        ...

class AzureOpenAIClient(LLMClient):
    """Azure OpenAI implementation."""

    def __init__(self, endpoint: str, deployment: str, api_version: str):
        ...
```

---

## 2. Memory System

### 2.1 Database Schema

```sql
-- sessions table
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    name TEXT,
    codebase_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON DEFAULT '{}'
);

-- messages table
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSON DEFAULT '{}'
);

CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- token_usage table
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    model TEXT NOT NULL,
    cost_usd REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_token_usage_session ON token_usage(session_id);

-- context_refs table (tracks which RAG chunks were used)
CREATE TABLE context_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    chunk_id TEXT NOT NULL,
    relevance_score REAL,
    was_useful BOOLEAN DEFAULT NULL  -- feedback loop
);
```

### 2.2 Session Interface

```python
# openagent/memory/session.py

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3
import uuid

@dataclass
class Session:
    id: str
    name: str
    codebase_path: Path | None
    created_at: datetime
    last_accessed: datetime
    metadata: dict

class SessionManager:
    """Manages session lifecycle and persistence."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def create(self, name: str = None, codebase_path: Path = None) -> Session:
        """Create new session."""
        ...

    def load(self, session_id: str) -> Session:
        """Load existing session."""
        ...

    def list_all(self) -> list[Session]:
        """List all sessions."""
        ...

    def delete(self, session_id: str) -> None:
        """Delete session and all associated data."""
        ...

    def get_recent(self, limit: int = 10) -> list[Session]:
        """Get most recently accessed sessions."""
        ...
```

### 2.3 Conversation History

```python
# openagent/memory/conversation.py

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Role = Literal["user", "assistant", "system", "tool"]

@dataclass
class Message:
    id: int
    role: Role
    content: str
    token_count: int
    created_at: datetime
    metadata: dict

class ConversationHistory:
    """Manages message history for a session."""

    def __init__(self, session: Session, db_path: Path):
        self.session = session
        self.db_path = db_path

    def add(self, role: Role, content: str, metadata: dict = None) -> Message:
        """Add message to history."""
        ...

    def get_all(self) -> list[Message]:
        """Get all messages in session."""
        ...

    def get_recent(self, limit: int = 20) -> list[Message]:
        """Get most recent messages."""
        ...

    def get_context_window(self, max_tokens: int) -> list[Message]:
        """Get messages that fit within token budget."""
        ...

    def to_llm_format(self, messages: list[Message] = None) -> list[dict]:
        """Convert to LLM API format."""
        return [{"role": m.role, "content": m.content} for m in messages]
```

### 2.4 Context Management

```python
# openagent/memory/context.py

from dataclasses import dataclass

@dataclass
class ContextConfig:
    max_tokens: int = 8000
    recent_messages: int = 10
    include_system: bool = True
    summarize_threshold: int = 20  # summarize after N messages

class ContextManager:
    """Builds optimal context for LLM calls."""

    def __init__(self, config: ContextConfig):
        self.config = config

    def build_context(
        self,
        history: ConversationHistory,
        rag_chunks: list[str] = None,
        system_prompt: str = None,
    ) -> list[dict]:
        """
        Build context that fits within token budget.

        Priority:
        1. System prompt
        2. RAG chunks (most relevant)
        3. Recent messages
        4. Summarized older context
        """
        ...

    def should_summarize(self, history: ConversationHistory) -> bool:
        """Check if history should be summarized."""
        ...

    async def summarize(self, messages: list[Message]) -> str:
        """Summarize older messages to save tokens."""
        ...
```

---

## 3. Token Tracking

### 3.1 Token Tracker

```python
# openagent/telemetry/tokens.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

# Pricing per 1M tokens (as of 2024)
MODEL_PRICING = {
    "gpt-4": {"input": 30.0, "output": 60.0},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    model: str
    timestamp: datetime = field(default_factory=datetime.now)
    request_id: str = ""

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def estimated_cost(self) -> float:
        """Estimate cost in USD."""
        pricing = MODEL_PRICING.get(self.model, {"input": 10.0, "output": 30.0})
        input_cost = (self.input_tokens / 1_000_000) * pricing["input"]
        output_cost = (self.output_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

@dataclass
class SessionTokenStats:
    total_input: int = 0
    total_output: int = 0
    total_cost: float = 0.0
    request_count: int = 0

    @property
    def total_tokens(self) -> int:
        return self.total_input + self.total_output

class TokenTracker:
    """Tracks token usage across session."""

    def __init__(self, session_id: str, db_path: Path, budget: int = None):
        self.session_id = session_id
        self.db_path = db_path
        self.budget = budget
        self._listeners: list[Callable] = []

    def record(self, usage: TokenUsage) -> None:
        """Record token usage to database."""
        ...

    def get_session_stats(self) -> SessionTokenStats:
        """Get aggregate stats for current session."""
        ...

    def get_budget_remaining(self) -> int | None:
        """Get remaining token budget, if set."""
        if self.budget is None:
            return None
        return max(0, self.budget - self.get_session_stats().total_tokens)

    def get_budget_percentage(self) -> float | None:
        """Get percentage of budget used."""
        if self.budget is None:
            return None
        stats = self.get_session_stats()
        return min(100.0, (stats.total_tokens / self.budget) * 100)

    def subscribe(self, callback: Callable[[TokenUsage], None]) -> None:
        """Subscribe to token usage updates."""
        self._listeners.append(callback)

    def _notify(self, usage: TokenUsage) -> None:
        """Notify all listeners of new usage."""
        for listener in self._listeners:
            listener(usage)
```

---

## 4. JSON-RPC Server

### 4.1 Protocol Definition

```python
# openagent/server/protocol.py

from dataclasses import dataclass
from typing import Any, Literal

@dataclass
class Request:
    jsonrpc: Literal["2.0"] = "2.0"
    method: str = ""
    params: dict = None
    id: int | str = None

@dataclass
class Response:
    jsonrpc: Literal["2.0"] = "2.0"
    result: Any = None
    error: dict = None
    id: int | str = None

@dataclass
class Notification:
    """Server-initiated message (no id, no response expected)."""
    jsonrpc: Literal["2.0"] = "2.0"
    method: str = ""
    params: dict = None
```

### 4.2 Server Implementation

```python
# openagent/server/jsonrpc.py

import asyncio
import json
import sys
from typing import Callable, Awaitable

Handler = Callable[[dict], Awaitable[Any]]

class JSONRPCServer:
    """JSON-RPC 2.0 server over stdio."""

    def __init__(self):
        self._handlers: dict[str, Handler] = {}
        self._running = False

    def register(self, method: str, handler: Handler) -> None:
        """Register method handler."""
        self._handlers[method] = handler

    async def run(self) -> None:
        """Main server loop - read from stdin, write to stdout."""
        self._running = True
        reader = asyncio.StreamReader()
        await asyncio.get_event_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader),
            sys.stdin
        )

        while self._running:
            line = await reader.readline()
            if not line:
                break

            try:
                request = json.loads(line.decode())
                response = await self._handle(request)
                if response:  # Not a notification
                    self._write(response)
            except Exception as e:
                self._write_error(-32603, str(e), request.get("id"))

    async def _handle(self, request: dict) -> dict | None:
        """Handle single request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        handler = self._handlers.get(method)
        if not handler:
            return self._error(-32601, f"Method not found: {method}", request_id)

        try:
            result = await handler(params)
            if request_id is None:  # Notification
                return None
            return {"jsonrpc": "2.0", "result": result, "id": request_id}
        except Exception as e:
            return self._error(-32603, str(e), request_id)

    def notify(self, method: str, params: dict) -> None:
        """Send notification to client."""
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, data: dict) -> None:
        """Write JSON line to stdout."""
        sys.stdout.write(json.dumps(data) + "\n")
        sys.stdout.flush()

    def _error(self, code: int, message: str, request_id) -> dict:
        return {
            "jsonrpc": "2.0",
            "error": {"code": code, "message": message},
            "id": request_id
        }
```

### 4.3 API Methods

```python
# openagent/server/handlers.py

"""
JSON-RPC method handlers.

Methods:
  chat.send(message: str) -> AsyncIterator[chunk]
  chat.cancel() -> bool

  session.create(name?: str, codebase_path?: str) -> Session
  session.load(id: str) -> Session
  session.list() -> list[Session]
  session.delete(id: str) -> bool

  tokens.get() -> SessionTokenStats
  tokens.set_budget(tokens: int) -> bool

  tools.list() -> list[Tool]
  tools.call(name: str, params: dict) -> Any

Notifications (server -> client):
  token_update(stats: SessionTokenStats)
  response_chunk(chunk: str)
  tool_call(name: str, params: dict)
  tool_result(name: str, result: Any)
"""

class Handlers:
    def __init__(self, agent: Agent):
        self.agent = agent
        self._current_task: asyncio.Task = None

    async def chat_send(self, params: dict) -> None:
        """Process chat message, stream response via notifications."""
        message = params["message"]

        async for chunk in self.agent.chat(message):
            self.server.notify("response_chunk", {"chunk": chunk})

        # Send final token update
        stats = self.agent.tokens.get_session_stats()
        self.server.notify("token_update", {
            "total": stats.total_tokens,
            "input": stats.total_input,
            "output": stats.total_output,
            "cost": stats.total_cost,
        })

    async def chat_cancel(self, params: dict) -> bool:
        """Cancel current chat request."""
        if self._current_task:
            self._current_task.cancel()
            return True
        return False

    async def session_create(self, params: dict) -> dict:
        """Create new session."""
        session = self.agent.session_manager.create(
            name=params.get("name"),
            codebase_path=params.get("codebase_path"),
        )
        return session.__dict__

    # ... other handlers
```

---

## 5. MCP Integration

### 5.1 MCP Host

```python
# openagent/tools/mcp_host.py

from dataclasses import dataclass
from typing import Any
import subprocess
import json

@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    server: str  # which MCP server provides this

@dataclass
class ToolResult:
    success: bool
    output: Any
    error: str | None = None

class MCPHost:
    """Hosts and communicates with MCP servers."""

    def __init__(self):
        self._servers: dict[str, subprocess.Popen] = {}
        self._tools: dict[str, Tool] = {}

    async def start_server(self, name: str, command: list[str]) -> None:
        """Start an MCP server process."""
        ...

    async def discover_tools(self, server: str) -> list[Tool]:
        """Discover tools from an MCP server."""
        ...

    async def call_tool(self, name: str, params: dict) -> ToolResult:
        """Call a tool on its MCP server."""
        tool = self._tools.get(name)
        if not tool:
            return ToolResult(False, None, f"Unknown tool: {name}")

        # Send request to server
        ...

    async def shutdown(self) -> None:
        """Shutdown all MCP servers."""
        for server in self._servers.values():
            server.terminate()
```

### 5.2 Tool Executor

```python
# openagent/tools/executor.py

from dataclasses import dataclass
from typing import AsyncIterator

@dataclass
class ToolCall:
    name: str
    params: dict
    reasoning: str  # why the agent chose this tool

@dataclass
class ExecutionStep:
    tool_call: ToolCall
    result: ToolResult
    tokens_used: int

class ToolExecutor:
    """Executes tools based on agent decisions."""

    def __init__(self, mcp_host: MCPHost, max_iterations: int = 10):
        self.mcp = mcp_host
        self.max_iterations = max_iterations

    async def execute_loop(
        self,
        initial_query: str,
        intent: Intent,
        context: list[dict],
    ) -> AsyncIterator[ExecutionStep | str]:
        """
        Execute tool loop until task complete or max iterations.

        Yields:
            ExecutionStep for each tool call
            str for final response chunks
        """
        iterations = 0

        while iterations < self.max_iterations:
            # Ask LLM what tool to use (or respond directly)
            decision = await self._get_next_action(context)

            if decision.action == "respond":
                async for chunk in decision.response:
                    yield chunk
                return

            # Execute tool
            result = await self.mcp.call_tool(
                decision.tool_name,
                decision.tool_params
            )

            yield ExecutionStep(
                tool_call=ToolCall(
                    decision.tool_name,
                    decision.tool_params,
                    decision.reasoning
                ),
                result=result,
                tokens_used=decision.tokens
            )

            # Add result to context
            context.append({
                "role": "tool",
                "content": json.dumps(result.__dict__)
            })

            iterations += 1

        yield "Max iterations reached without completion."
```

---

## 6. Rust TUI

### 6.1 Project Structure

```
TUI/
├── Cargo.toml
├── src/
│   ├── main.rs              # Entry point
│   ├── app.rs               # Application state
│   ├── ui/
│   │   ├── mod.rs
│   │   ├── layout.rs        # Main layout
│   │   ├── chat.rs          # Chat pane
│   │   ├── input.rs         # Input bar
│   │   ├── tokens.rs        # Token monitor widget
│   │   ├── files.rs         # File tree (optional)
│   │   └── status.rs        # Status bar
│   ├── backend/
│   │   ├── mod.rs
│   │   ├── process.rs       # Python process management
│   │   └── jsonrpc.rs       # JSON-RPC client
│   ├── events/
│   │   ├── mod.rs
│   │   └── handler.rs       # Event handling
│   └── config.rs            # Configuration
└── tests/
    ├── ui_tests.rs
    └── backend_tests.rs
```

### 6.2 Application State

```rust
// src/app.rs

use std::collections::VecDeque;

#[derive(Debug, Clone)]
pub struct Message {
    pub role: Role,
    pub content: String,
    pub timestamp: chrono::DateTime<chrono::Utc>,
}

#[derive(Debug, Clone, Copy)]
pub enum Role {
    User,
    Assistant,
    System,
    Tool,
}

#[derive(Debug, Default)]
pub struct TokenStats {
    pub session_total: u64,
    pub last_input: u64,
    pub last_output: u64,
    pub cost_usd: f64,
    pub budget: Option<u64>,
}

impl TokenStats {
    pub fn budget_percentage(&self) -> Option<f64> {
        self.budget.map(|b| (self.session_total as f64 / b as f64) * 100.0)
    }
}

pub struct App {
    pub messages: VecDeque<Message>,
    pub input: String,
    pub input_history: Vec<String>,
    pub history_index: Option<usize>,
    pub tokens: TokenStats,
    pub session_id: Option<String>,
    pub is_loading: bool,
    pub show_file_tree: bool,
    pub scroll_offset: usize,
}

impl App {
    pub fn new() -> Self {
        Self {
            messages: VecDeque::new(),
            input: String::new(),
            input_history: Vec::new(),
            history_index: None,
            tokens: TokenStats::default(),
            session_id: None,
            is_loading: false,
            show_file_tree: false,
            scroll_offset: 0,
        }
    }

    pub fn add_message(&mut self, role: Role, content: String) {
        self.messages.push_back(Message {
            role,
            content,
            timestamp: chrono::Utc::now(),
        });
    }

    pub fn update_tokens(&mut self, stats: TokenStats) {
        self.tokens = stats;
    }
}
```

### 6.3 Token Monitor Widget

```rust
// src/ui/tokens.rs

use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::{Color, Style},
    widgets::{Block, Borders, Gauge, Paragraph, Widget},
};

use crate::app::TokenStats;

pub struct TokenMonitor<'a> {
    stats: &'a TokenStats,
}

impl<'a> TokenMonitor<'a> {
    pub fn new(stats: &'a TokenStats) -> Self {
        Self { stats }
    }
}

impl<'a> Widget for TokenMonitor<'a> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let block = Block::default()
            .borders(Borders::ALL)
            .title("Tokens");

        let inner = block.inner(area);
        block.render(area, buf);

        // Token count
        let count_text = format!("{:.1}k", self.stats.session_total as f64 / 1000.0);
        let count = Paragraph::new(count_text)
            .style(Style::default().fg(Color::White));
        count.render(Rect::new(inner.x, inner.y, inner.width, 1), buf);

        // Progress bar (if budget set)
        if let Some(pct) = self.stats.budget_percentage() {
            let color = if pct > 90.0 {
                Color::Red
            } else if pct > 70.0 {
                Color::Yellow
            } else {
                Color::Green
            };

            let gauge = Gauge::default()
                .ratio(pct.min(100.0) / 100.0)
                .gauge_style(Style::default().fg(color));
            gauge.render(Rect::new(inner.x, inner.y + 1, inner.width, 1), buf);
        }

        // Cost
        let cost_text = format!("${:.2}", self.stats.cost_usd);
        let cost = Paragraph::new(cost_text)
            .style(Style::default().fg(Color::DarkGray));
        cost.render(Rect::new(inner.x, inner.y + 2, inner.width, 1), buf);
    }
}
```

### 6.4 Python Process Management

```rust
// src/backend/process.rs

use std::process::{Child, Command, Stdio};
use std::io::{BufRead, BufReader, Write};
use tokio::sync::mpsc;

pub struct PythonBackend {
    process: Child,
    tx: mpsc::Sender<String>,
    rx: mpsc::Receiver<String>,
}

impl PythonBackend {
    pub fn spawn() -> Result<Self, std::io::Error> {
        let mut process = Command::new("python")
            .args(["-m", "openagent.server"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;

        // Set up channels for async communication
        let (tx, rx) = mpsc::channel(100);

        // Spawn reader thread
        let stdout = process.stdout.take().unwrap();
        let tx_clone = tx.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(line) = line {
                    let _ = tx_clone.blocking_send(line);
                }
            }
        });

        Ok(Self { process, tx, rx })
    }

    pub fn send(&mut self, request: &str) -> Result<(), std::io::Error> {
        if let Some(stdin) = &mut self.process.stdin {
            writeln!(stdin, "{}", request)?;
            stdin.flush()?;
        }
        Ok(())
    }

    pub async fn recv(&mut self) -> Option<String> {
        self.rx.recv().await
    }

    pub fn is_alive(&mut self) -> bool {
        matches!(self.process.try_wait(), Ok(None))
    }

    pub fn restart(&mut self) -> Result<(), std::io::Error> {
        let _ = self.process.kill();
        *self = Self::spawn()?;
        Ok(())
    }
}
```

### 6.5 Main Layout

```rust
// src/ui/layout.rs

use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    Frame,
};

use crate::app::App;
use super::{chat::ChatPane, input::InputBar, tokens::TokenMonitor, files::FileTree};

pub fn draw(frame: &mut Frame, app: &App) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Length(20),  // Left sidebar
            Constraint::Min(40),     // Main content
        ])
        .split(frame.area());

    // Left sidebar: token monitor + file tree
    let left_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(5),   // Token monitor
            Constraint::Min(10),     // File tree
        ])
        .split(chunks[0]);

    // Token monitor (top left)
    let token_monitor = TokenMonitor::new(&app.tokens);
    frame.render_widget(token_monitor, left_chunks[0]);

    // File tree (optional)
    if app.show_file_tree {
        let file_tree = FileTree::new();
        frame.render_widget(file_tree, left_chunks[1]);
    }

    // Main content: chat + input
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(5),      // Chat pane
            Constraint::Length(3),   // Input bar
        ])
        .split(chunks[1]);

    // Chat pane
    let chat = ChatPane::new(&app.messages, app.scroll_offset);
    frame.render_widget(chat, main_chunks[0]);

    // Input bar
    let input = InputBar::new(&app.input, app.is_loading);
    frame.render_widget(input, main_chunks[1]);
}
```

---

## 7. Testing Requirements

### 7.1 Python Tests

```
tests/python/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── test_intent.py       # Intent extraction
│   ├── test_llm.py          # LLM client
│   ├── test_session.py      # Session management
│   ├── test_conversation.py # Message history
│   ├── test_tokens.py       # Token tracking
│   ├── test_context.py      # Context management
│   ├── test_jsonrpc.py      # Protocol handling
│   └── test_mcp.py          # MCP host
├── integration/
│   ├── test_agent_flow.py   # Full agent flow
│   ├── test_rag.py          # ChromaDB integration
│   └── test_tools.py        # Tool execution
└── fixtures/
    ├── sample_codebase/     # Test files
    └── mock_responses.json  # LLM response mocks
```

**Example Test**:

```python
# tests/python/unit/test_tokens.py

import pytest
from datetime import datetime
from openagent.telemetry.tokens import TokenUsage, TokenTracker, SessionTokenStats

class TestTokenUsage:
    def test_total_calculation(self):
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=200,
            model="gpt-4o-mini"
        )
        assert usage.total == 300

    def test_cost_estimation_gpt4o_mini(self):
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="gpt-4o-mini"
        )
        # $0.15/M input + $0.60/M output = $0.75
        assert usage.estimated_cost() == pytest.approx(0.75, rel=0.01)

    def test_cost_estimation_unknown_model(self):
        usage = TokenUsage(
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            model="unknown-model"
        )
        # Should use default pricing
        assert usage.estimated_cost() > 0

class TestTokenTracker:
    @pytest.fixture
    def tracker(self, tmp_path):
        db_path = tmp_path / "test.db"
        return TokenTracker("test-session", db_path)

    def test_record_and_retrieve(self, tracker):
        usage = TokenUsage(100, 200, "gpt-4o-mini")
        tracker.record(usage)

        stats = tracker.get_session_stats()
        assert stats.total_input == 100
        assert stats.total_output == 200
        assert stats.request_count == 1

    def test_budget_tracking(self, tracker):
        tracker.budget = 1000

        usage = TokenUsage(300, 200, "gpt-4o-mini")
        tracker.record(usage)

        assert tracker.get_budget_remaining() == 500
        assert tracker.get_budget_percentage() == pytest.approx(50.0)

    def test_subscriber_notification(self, tracker):
        received = []
        tracker.subscribe(lambda u: received.append(u))

        usage = TokenUsage(100, 200, "gpt-4o-mini")
        tracker.record(usage)

        assert len(received) == 1
        assert received[0].total == 300
```

### 7.2 Rust Tests

```rust
// TUI/src/ui/tokens.rs

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::buffer::Buffer;
    use ratatui::layout::Rect;

    #[test]
    fn test_token_monitor_renders() {
        let stats = TokenStats {
            session_total: 2400,
            last_input: 150,
            last_output: 320,
            cost_usd: 0.04,
            budget: Some(10000),
        };

        let widget = TokenMonitor::new(&stats);
        let area = Rect::new(0, 0, 15, 5);
        let mut buf = Buffer::empty(area);

        widget.render(area, &mut buf);

        // Verify content was rendered
        let content = buf.content().iter()
            .map(|c| c.symbol())
            .collect::<String>();

        assert!(content.contains("2.4k"));
        assert!(content.contains("$0.04"));
    }

    #[test]
    fn test_budget_percentage_calculation() {
        let stats = TokenStats {
            session_total: 5000,
            budget: Some(10000),
            ..Default::default()
        };

        assert_eq!(stats.budget_percentage(), Some(50.0));
    }

    #[test]
    fn test_budget_percentage_none_when_no_budget() {
        let stats = TokenStats {
            session_total: 5000,
            budget: None,
            ..Default::default()
        };

        assert_eq!(stats.budget_percentage(), None);
    }
}
```

---

## 8. Configuration

### 8.1 Config File Format

```toml
# ~/.config/openagent/config.toml

[llm]
provider = "azure"  # azure, openai, anthropic
model = "gpt-4o-mini"
endpoint = "${AZURE_OPENAI_ENDPOINT}"
api_key = "${AZURE_OPENAI_KEY}"
max_tokens = 4096
temperature = 0.7

[tokens]
budget = 100000  # per session, optional
warn_at = 80     # warn at 80% of budget

[session]
db_path = "~/.local/share/openagent/sessions.db"
auto_save = true

[rag]
db_path = "~/.local/share/openagent/chroma"
collection = "codebase_specs"

[tui]
theme = "dark"
show_file_tree = false
vim_mode = true

[tui.keybindings]
quit = "q"
toggle_file_tree = "ctrl+b"
scroll_up = "k"
scroll_down = "j"
submit = "enter"
cancel = "ctrl+c"
```

### 8.2 Environment Variables

```bash
# Required
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_KEY=your-api-key

# Optional
OPENAGENT_CONFIG=~/.config/openagent/config.toml
OPENAGENT_LOG_LEVEL=info
OPENAGENT_SESSION_DB=~/.local/share/openagent/sessions.db
```

---

## Summary

This spec defines a complete system with:

1. **Python Core**: Modular package with clear interfaces
2. **Memory System**: SQLite-backed sessions and conversations
3. **Token Tracking**: Real-time usage monitoring with cost estimation
4. **JSON-RPC Server**: IPC between Rust TUI and Python backend
5. **MCP Integration**: Standardized tool interface
6. **Rust TUI**: Interactive terminal with token monitor
7. **Testing**: Comprehensive test requirements for all components
8. **Configuration**: Flexible config via TOML and environment

Each component is designed to be independently testable and replaceable.
