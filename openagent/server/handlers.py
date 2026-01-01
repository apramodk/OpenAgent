"""JSON-RPC method handlers."""

from pathlib import Path
from typing import Any

from openagent.core.agent import Agent, AgentConfig
from openagent.memory.session import SessionManager, Session
from openagent.telemetry.tokens import TokenTracker
from openagent.rag.store import RAGStore, Chunk, ChunkMetadata
from openagent.rag.query import RAGQuery
from openagent.rag.scanner import scan_and_generate_chunks


class Handlers:
    """Container for all JSON-RPC handlers."""

    def __init__(
        self,
        agent: Agent | None = None,
        session_manager: SessionManager | None = None,
        rag_store: RAGStore | None = None,
        rag_query: RAGQuery | None = None,
    ):
        self.agent = agent
        self.session_manager = session_manager
        self.rag_store = rag_store
        self.rag_query = rag_query
        self._current_session: Session | None = None

    async def chat_send(self, params: dict) -> dict:
        """Process a chat message with optional RAG context."""
        if not self.agent:
            return {"error": "Agent not initialized"}

        message = params.get("message", "")
        if not message:
            return {"error": "No message provided"}

        use_rag = params.get("use_rag", True)  # Default to using RAG if available

        try:
            if use_rag and self.rag_query:
                # Use RAG-enhanced chat
                response = await self.agent.chat_with_rag(message, self.rag_query)
            else:
                # Regular chat without RAG
                response = await self.agent.chat(message)
        except Exception as e:
            error_msg = str(e)
            # Provide helpful message for common issues
            if "PROJECT_ENDPOINT" in error_msg or "credential" in error_msg.lower():
                return {
                    "response": f"LLM not configured. Set PROJECT_ENDPOINT in .env file.\n\nError: {error_msg}",
                    "tokens": None,
                }
            return {
                "response": f"Error calling LLM: {error_msg}",
                "tokens": None,
            }

        # Get token stats if available
        stats = None
        if self.agent.token_tracker:
            s = self.agent.token_tracker.get_session_stats()
            stats = s.to_dict()

        return {
            "response": response,
            "tokens": stats,
        }

    async def chat_cancel(self, params: dict) -> dict:
        """Cancel current chat request."""
        # TODO: Implement cancellation
        return {"cancelled": False}

    async def session_create(self, params: dict) -> dict:
        """Create a new session."""
        if not self.session_manager:
            return {"error": "Session manager not initialized"}

        name = params.get("name")
        codebase_path = params.get("codebase_path")

        session = self.session_manager.create(
            name=name,
            codebase_path=codebase_path,
        )
        self._current_session = session

        # Initialize agent with new session
        self._init_agent(session)

        return session.to_dict()

    async def session_load(self, params: dict) -> dict:
        """Load an existing session."""
        if not self.session_manager:
            return {"error": "Session manager not initialized"}

        session_id = params.get("id")
        if not session_id:
            return {"error": "No session ID provided"}

        session = self.session_manager.load(session_id)
        if not session:
            return {"error": f"Session not found: {session_id}"}

        self._current_session = session
        self._init_agent(session)

        return session.to_dict()

    async def session_list(self, params: dict) -> dict:
        """List all sessions."""
        if not self.session_manager:
            return {"error": "Session manager not initialized"}

        limit = params.get("limit", 20)
        sessions = self.session_manager.get_recent(limit)

        return {
            "sessions": [s.to_dict() for s in sessions],
        }

    async def session_delete(self, params: dict) -> dict:
        """Delete a session."""
        if not self.session_manager:
            return {"error": "Session manager not initialized"}

        session_id = params.get("id")
        if not session_id:
            return {"error": "No session ID provided"}

        deleted = self.session_manager.delete(session_id)
        return {"deleted": deleted}

    async def tokens_get(self, params: dict) -> dict:
        """Get current token usage."""
        if not self.agent or not self.agent.token_tracker:
            return {
                "total_input": 0,
                "total_output": 0,
                "total_tokens": 0,
                "total_cost": 0,
                "request_count": 0,
            }

        stats = self.agent.token_tracker.get_session_stats()
        result = stats.to_dict()

        # Add budget info if set
        if self.agent.token_tracker.budget:
            result["budget"] = self.agent.token_tracker.budget
            result["budget_remaining"] = self.agent.token_tracker.get_budget_remaining()
            result["budget_percentage"] = self.agent.token_tracker.get_budget_percentage()

        return result

    async def tokens_set_budget(self, params: dict) -> dict:
        """Set token budget."""
        if not self.agent or not self.agent.token_tracker:
            return {"error": "Token tracker not initialized"}

        budget = params.get("budget")
        self.agent.token_tracker.budget = budget

        return {"budget": budget}

    async def tools_list(self, params: dict) -> dict:
        """List available tools."""
        # TODO: Implement when tool registry is connected
        return {"tools": []}

    async def tools_call(self, params: dict) -> dict:
        """Call a tool directly."""
        # TODO: Implement when tool executor is connected
        return {"error": "Not implemented"}

    async def rag_search(self, params: dict) -> dict:
        """Search the RAG store for relevant code chunks."""
        if not self.rag_query:
            return {"error": "RAG not initialized", "results": []}

        query = params.get("query", "")
        if not query:
            return {"error": "No query provided", "results": []}

        n_results = params.get("n_results", 5)
        chunk_type = params.get("type")  # Optional filter

        try:
            if chunk_type:
                results = self.rag_query.search_by_type(query, chunk_type, n_results)
            else:
                results = self.rag_query.search(query, n_results)

            return {
                "results": [
                    {
                        "id": r.chunk.id,
                        "content": r.chunk.content,
                        "score": r.score,
                        "relevance": r.relevance,
                        "metadata": {
                            "path": r.chunk.metadata.path,
                            "type": r.chunk.metadata.chunk_type,
                            "language": r.chunk.metadata.language,
                            "signature": r.chunk.metadata.signature,
                            "concepts": r.chunk.metadata.concepts,
                        },
                    }
                    for r in results
                ],
                "count": len(results),
            }
        except Exception as e:
            return {"error": str(e), "results": []}

    async def rag_ingest(self, params: dict) -> dict:
        """Ingest chunks into the RAG store."""
        if not self.rag_store:
            return {"error": "RAG store not initialized", "ingested": 0}

        chunks_data = params.get("chunks", [])
        if not chunks_data:
            # Try loading from JSON file
            json_path = params.get("json_path")
            if json_path:
                try:
                    count = self.rag_store.load_from_json(json_path)
                    return {"ingested": count, "source": "json_file"}
                except Exception as e:
                    return {"error": str(e), "ingested": 0}
            return {"error": "No chunks or json_path provided", "ingested": 0}

        try:
            chunks = []
            for c in chunks_data:
                metadata = c.get("metadata", {})
                chunks.append(
                    Chunk(
                        id=c["id"],
                        content=c["content"],
                        metadata=ChunkMetadata(
                            path=metadata.get("path", ""),
                            language=metadata.get("language", ""),
                            chunk_type=metadata.get("type", ""),
                            concepts=metadata.get("concepts", []),
                            calls=metadata.get("calls", []),
                            called_by=metadata.get("called_by", []),
                            signature=metadata.get("signature", ""),
                        ),
                    )
                )

            self.rag_store.add_batch(chunks)
            return {"ingested": len(chunks), "source": "direct"}
        except Exception as e:
            return {"error": str(e), "ingested": 0}

    async def rag_status(self, params: dict) -> dict:
        """Get RAG store status."""
        if not self.rag_store:
            return {"initialized": False, "count": 0}

        return {
            "initialized": True,
            "count": self.rag_store.count(),
            "db_path": str(self.rag_store.db_path),
            "collection": self.rag_store.collection_name,
        }

    async def codebase_init(self, params: dict) -> dict:
        """
        Initialize RAG by scanning a codebase.

        Scans the codebase directory, extracts semantic information from code files,
        and ingests them into the RAG store.
        """
        if not self.rag_store:
            return {"error": "RAG store not initialized", "chunks": 0}

        codebase_path = params.get("path")
        if not codebase_path:
            # Try to get from current session
            if self._current_session and self._current_session.codebase_path:
                codebase_path = self._current_session.codebase_path
            else:
                return {"error": "No codebase path provided", "chunks": 0}

        path = Path(codebase_path)
        if not path.exists():
            return {"error": f"Path does not exist: {codebase_path}", "chunks": 0}

        if not path.is_dir():
            return {"error": f"Path is not a directory: {codebase_path}", "chunks": 0}

        try:
            # Clear existing chunks for this codebase (optional, based on params)
            if params.get("clear", False):
                self.rag_store.clear()

            # Scan and generate chunks
            chunks, stats = scan_and_generate_chunks(path)

            if not chunks:
                return {
                    "chunks": 0,
                    "stats": stats,
                    "message": "No code files found to index",
                }

            # Ingest chunks
            self.rag_store.add_batch(chunks)

            return {
                "chunks": len(chunks),
                "stats": stats,
                "message": f"Indexed {stats['files_scanned']} files, {stats['units_extracted']} code units",
            }

        except Exception as e:
            return {"error": str(e), "chunks": 0}

    def _init_agent(self, session: Session) -> None:
        """Initialize agent for a session."""
        db_path = self.session_manager.db_path if self.session_manager else Path("sessions.db")

        token_tracker = TokenTracker(
            session_id=session.id,
            db_path=db_path,
        )

        config = AgentConfig(
            system_prompt="You are a helpful AI assistant for understanding codebases.",
        )

        self.agent = Agent(
            config=config,
            token_tracker=token_tracker,
        )


def create_handlers(
    db_path: Path | str | None = None,
    rag_db_path: Path | str | None = None,
) -> dict:
    """Create handler functions dictionary for JSON-RPC server."""
    if db_path is None:
        db_path = Path.home() / ".local/share/openagent/sessions.db"

    if rag_db_path is None:
        rag_db_path = Path.home() / ".local/share/openagent/chroma_db"

    session_manager = SessionManager(db_path)

    # Initialize RAG components
    try:
        rag_store = RAGStore(db_path=rag_db_path)
        rag_query = RAGQuery(db_path=rag_db_path)
    except Exception as e:
        print(f"Warning: Could not initialize RAG: {e}")
        rag_store = None
        rag_query = None

    handlers = Handlers(
        session_manager=session_manager,
        rag_store=rag_store,
        rag_query=rag_query,
    )

    return {
        "chat.send": handlers.chat_send,
        "chat.cancel": handlers.chat_cancel,
        "session.create": handlers.session_create,
        "session.load": handlers.session_load,
        "session.list": handlers.session_list,
        "session.delete": handlers.session_delete,
        "tokens.get": handlers.tokens_get,
        "tokens.set_budget": handlers.tokens_set_budget,
        "tools.list": handlers.tools_list,
        "tools.call": handlers.tools_call,
        "rag.search": handlers.rag_search,
        "rag.ingest": handlers.rag_ingest,
        "rag.status": handlers.rag_status,
        "codebase.init": handlers.codebase_init,
    }
