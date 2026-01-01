"""JSON-RPC method handlers."""

import hashlib
from pathlib import Path
from typing import Any, Callable, Awaitable

from openagent.core.agent import Agent, AgentConfig
from openagent.memory.session import SessionManager, Session
from openagent.telemetry.tokens import TokenTracker
from openagent.rag.store import RAGStore, Chunk, ChunkMetadata
from openagent.rag.query import RAGQuery
from openagent.rag.scanner import scan_and_generate_chunks

# Type for async notification sender
NotifySender = Callable[[str, dict], Awaitable[None]]


def get_collection_name_for_path(codebase_path: str) -> str:
    """Generate a unique collection name for a codebase path."""
    # Use hash of absolute path to create unique but consistent name
    path_hash = hashlib.sha256(codebase_path.encode()).hexdigest()[:12]
    # Get the directory name for readability
    dir_name = Path(codebase_path).name.lower()
    # Sanitize: only alphanumeric and underscore
    dir_name = "".join(c if c.isalnum() else "_" for c in dir_name)[:20]
    return f"codebase_{dir_name}_{path_hash}"


class Handlers:
    """Container for all JSON-RPC handlers."""

    def __init__(
        self,
        agent: Agent | None = None,
        session_manager: SessionManager | None = None,
        rag_store: RAGStore | None = None,
        rag_query: RAGQuery | None = None,
        rag_db_path: Path | str | None = None,
        notify: NotifySender | None = None,
    ):
        self.agent = agent
        self.session_manager = session_manager
        self.rag_store = rag_store
        self.rag_query = rag_query
        self.rag_db_path = Path(rag_db_path) if rag_db_path else Path.home() / ".local/share/openagent/chroma_db"
        self._current_session: Session | None = None
        self._current_codebase_path: str | None = None
        self._notify = notify  # For sending streaming notifications

    def _switch_rag_collection(self, codebase_path: str) -> None:
        """Switch to RAG collection for the given codebase path."""
        if self._current_codebase_path == codebase_path:
            return  # Already using this collection

        collection_name = get_collection_name_for_path(codebase_path)

        try:
            self.rag_store = RAGStore(
                db_path=self.rag_db_path,
                collection_name=collection_name,
            )
            self.rag_query = RAGQuery(store=self.rag_store)
            self._current_codebase_path = codebase_path
        except Exception as e:
            print(f"Warning: Could not switch RAG collection: {e}")

    async def chat_send(self, params: dict) -> dict:
        """Process a chat message with streaming support."""
        if not self.agent:
            return {"error": "Agent not initialized"}

        message = params.get("message", "")
        if not message:
            return {"error": "No message provided"}

        use_rag = params.get("use_rag", True)  # Default to using RAG if available
        stream = params.get("stream", True)  # Default to streaming

        try:
            # Get RAG context if available
            rag_context = None
            if use_rag and self.rag_query:
                intent = self.agent.get_intent(message)
                query = intent.query if intent else message
                rag_context = self.rag_query.get_context_for_query(
                    query,
                    max_tokens=self.agent.context_manager.config.max_rag_tokens,
                )

            if stream and self._notify:
                # Stream the response
                full_response = ""
                async for chunk in self.agent.chat_stream(message, rag_context=rag_context):
                    full_response += chunk
                    # Send chunk notification
                    await self._notify("chat.stream", {"chunk": chunk})

                # Get token stats to include in done notification
                done_payload: dict = {"done": True}
                if self.agent.token_tracker:
                    stats = self.agent.token_tracker.get_session_stats()
                    done_payload["tokens"] = stats.to_dict()

                # Send stream end notification with token stats
                await self._notify("chat.stream", done_payload)
                response = full_response
            else:
                # Non-streaming fallback
                response = await self.agent.chat(message, rag_context=rag_context)

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

        # Switch to codebase-specific RAG collection
        if codebase_path:
            abs_path = str(Path(codebase_path).resolve())
            self._switch_rag_collection(abs_path)

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

        # Switch to codebase-specific RAG collection
        if session.codebase_path:
            abs_path = str(Path(session.codebase_path).resolve())
            self._switch_rag_collection(abs_path)

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

    async def model_get(self, params: dict) -> dict:
        """Get current model."""
        if not self.agent or not self.agent.llm:
            return {"error": "Agent not initialized", "model": None}

        return {"model": self.agent.llm.model}

    async def model_set(self, params: dict) -> dict:
        """Set the LLM model."""
        model = params.get("model")
        if not model:
            return {"error": "No model specified", "model": None}

        if not self.agent:
            return {"error": "Agent not initialized", "model": None}

        # Update the model on the LLM client
        old_model = self.agent.llm.model
        self.agent.llm.model = model
        self.agent.config.model = model

        return {
            "model": model,
            "previous": old_model,
        }

    async def model_list(self, params: dict) -> dict:
        """List available models (common Azure OpenAI deployments)."""
        # These are common deployment names - actual availability depends on Azure setup
        models = [
            {"id": "gpt-4o", "description": "GPT-4o - Latest multimodal model"},
            {"id": "gpt-4o-mini", "description": "GPT-4o Mini - Fast and efficient"},
            {"id": "gpt-4", "description": "GPT-4 - High capability"},
            {"id": "gpt-4-turbo", "description": "GPT-4 Turbo - Fast GPT-4"},
            {"id": "gpt-35-turbo", "description": "GPT-3.5 Turbo - Fast and cheap"},
            {"id": "o1-preview", "description": "O1 Preview - Reasoning model"},
            {"id": "o1-mini", "description": "O1 Mini - Smaller reasoning model"},
        ]
        return {"models": models}

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

    async def rag_embeddings(self, params: dict) -> dict:
        """Get embeddings projected to 2D for visualization."""
        if not self.rag_store:
            return {"error": "RAG not initialized", "points": []}

        try:
            # Get all embeddings from ChromaDB
            collection = self.rag_store._collection
            result = collection.get(include=["embeddings", "metadatas"])

            if not result["ids"] or not result["embeddings"]:
                return {"points": [], "count": 0}

            ids = result["ids"]
            embeddings = result["embeddings"]
            metadatas = result["metadatas"] or [{}] * len(ids)

            # Project to 2D using PCA
            import numpy as np

            embeddings_array = np.array(embeddings)

            if len(embeddings_array) < 2:
                # Not enough points for PCA, just use first 2 dims
                points_2d = embeddings_array[:, :2] if embeddings_array.shape[1] >= 2 else embeddings_array
            else:
                # Simple PCA: center and project to top 2 principal components
                centered = embeddings_array - np.mean(embeddings_array, axis=0)
                # Use SVD for PCA
                U, S, Vt = np.linalg.svd(centered, full_matrices=False)
                points_2d = centered @ Vt[:2].T

            # Normalize to 0-1 range
            if len(points_2d) > 0:
                min_vals = points_2d.min(axis=0)
                max_vals = points_2d.max(axis=0)
                range_vals = max_vals - min_vals
                range_vals[range_vals == 0] = 1  # Avoid division by zero
                points_2d = (points_2d - min_vals) / range_vals

            # Build response
            points = []
            for i, chunk_id in enumerate(ids):
                meta = metadatas[i] if i < len(metadatas) else {}
                points.append({
                    "id": chunk_id,
                    "x": float(points_2d[i][0]) if len(points_2d[i]) > 0 else 0.5,
                    "y": float(points_2d[i][1]) if len(points_2d[i]) > 1 else 0.5,
                    "path": meta.get("path", ""),
                    "type": meta.get("type", ""),
                })

            return {"points": points, "count": len(points)}

        except Exception as e:
            return {"error": str(e), "points": []}

    async def codebase_init(self, params: dict) -> dict:
        """
        Initialize RAG by scanning a codebase.

        Scans the codebase directory, extracts semantic information from code files,
        and ingests them into the RAG store.
        """
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

        # Switch to codebase-specific RAG collection
        abs_path = str(path.resolve())
        self._switch_rag_collection(abs_path)

        if not self.rag_store:
            return {"error": "RAG store not initialized", "chunks": 0}

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
        from openagent.core.llm import AzureOpenAIClient

        db_path = self.session_manager.db_path if self.session_manager else Path("sessions.db")

        token_tracker = TokenTracker(
            session_id=session.id,
            db_path=db_path,
        )

        # Create LLM client with env var defaults
        llm_client = AzureOpenAIClient()

        config = AgentConfig(
            system_prompt="You are a helpful AI assistant for understanding codebases.",
            model=llm_client.model,  # Use the actual model from client
        )

        self.agent = Agent(
            config=config,
            llm_client=llm_client,
            token_tracker=token_tracker,
        )


def create_handlers(
    db_path: Path | str | None = None,
    rag_db_path: Path | str | None = None,
    notify: NotifySender | None = None,
) -> dict:
    """Create handler functions dictionary for JSON-RPC server."""
    if db_path is None:
        db_path = Path.home() / ".local/share/openagent/sessions.db"

    if rag_db_path is None:
        rag_db_path = Path.home() / ".local/share/openagent/chroma_db"

    session_manager = SessionManager(db_path)

    # Initialize RAG components (default collection, will be switched per-codebase)
    try:
        rag_store = RAGStore(db_path=rag_db_path)
        rag_query = RAGQuery(store=rag_store)
    except Exception as e:
        print(f"Warning: Could not initialize RAG: {e}")
        rag_store = None
        rag_query = None

    handlers = Handlers(
        session_manager=session_manager,
        rag_store=rag_store,
        rag_query=rag_query,
        rag_db_path=rag_db_path,
        notify=notify,
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
        "model.get": handlers.model_get,
        "model.set": handlers.model_set,
        "model.list": handlers.model_list,
        "tools.list": handlers.tools_list,
        "tools.call": handlers.tools_call,
        "rag.search": handlers.rag_search,
        "rag.ingest": handlers.rag_ingest,
        "rag.status": handlers.rag_status,
        "rag.embeddings": handlers.rag_embeddings,
        "codebase.init": handlers.codebase_init,
    }
