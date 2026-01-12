# OpenAgent Improvements TODO

## 1. Testing Infrastructure
- [x] Implement isolated unit tests for `Agent` class using mocks. (Added tests/python/unit/test_agent.py)
- [x] Create a `MockLLMClient` to test orchestration logic without API calls. (Added to tests/conftest.py)
- [ ] Add unit tests for `ContextManager` logic (sliding window, summarization triggers).
- [ ] Setup a CI pipeline configuration (e.g., GitHub Actions) to run unit tests on push.

## 2. Dependency Injection & Coupling
- [x] Refactor `Agent` to remove default `AzureOpenAIClient` instantiation in `__init__`. (Completed)
- [x] Implement a Repository pattern for `ConversationHistory` to decouple logic from SQLite. (Refactored to abstract base class + SQLite implementation)
- [ ] Create a `StorageInterface` for memory management (SQLite, In-memory, Redis).

## 3. Asynchronous Implementation
- [x] Switch from sync OpenAI client to native `AsyncOpenAI` in `LLMClient`. (Implemented in openagent/core/llm.py)
- [x] Remove manual thread/queue bridging for streaming in `openagent/core/llm.py`. (Removed custom queue logic)
- [ ] Ensure all I/O operations (RAG scanning, file reading) are fully non-blocking.

## 4. Rust TUI Architecture
- [ ] Refactor `App` struct in `TUI/src/app.rs` into smaller, domain-specific components.
- [x] Extract `CommandParser` for slash command logic. (Created `TUI/src/command.rs` and `TUI/src/action.rs`)
- [ ] Extract `UIState` for focus and scroll management.
- [ ] Move backend communication logic into a dedicated `BackendClient` module.

## 5. Configuration Management
- [x] Centralize Python environment variable loading into `openagent/config.py`. (Updated `config.py` logic and `AzureOpenAIClient` to use it)
- [x] Pass configuration objects into clients/agents instead of reading `os.environ` inside classes.
- [x] Extract hardcoded constants (timings, layout sizes) in Rust TUI to a `config.rs`. (Created `TUI/src/config.rs` and updated `app.rs`/`main.rs`)

## 6. Error Handling & Telemetry
- [ ] Implement a structured event system in the TUI for errors and logs.
- [ ] Add a dedicated "Debug/Logs" view in the TUI.
- [ ] Improve error propagation from Python backend to Rust TUI with more descriptive JSON-RPC errors.

## 7. Codebase Structure
- [x] **Root Cleanup:** Move top-level scripts (`rag_init.py`, `rag_query.py`, `dspy_agent.py`) into a `scripts/` or `examples/` directory to declutter the root. (Moved to scripts/ and examples/prototype/)
- [ ] **Config Organization:** Move configuration files (like `semantics.json`) into a dedicated `config/` or `data/` directory.
- [ ] **Rust Workspace:** Consider converting the project to a Cargo Workspace, treating the root Rust crate and the `TUI` crate as members (e.g., move root `src/` to `crates/server` or `crates/bridge`).
- [ ] **Standardized Entry:** Consolidate Python entry points (currently `main.py` and others) into a standard `__main__.py` or `cli.py` within the `openagent` package.
