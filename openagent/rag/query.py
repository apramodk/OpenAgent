"""RAG query functionality."""

from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings

from openagent.rag.store import Chunk, ChunkMetadata


@dataclass
class QueryResult:
    """Result from a RAG query."""

    chunk: Chunk
    score: float  # Distance score (lower is more similar)

    @property
    def relevance(self) -> float:
        """Convert distance to relevance (0-1, higher is more relevant)."""
        # ChromaDB uses L2 distance by default
        # Convert to a 0-1 relevance score
        return 1.0 / (1.0 + self.score)


class RAGQuery:
    """Query interface for the RAG store."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        collection_name: str = "codebase_specs",
        store: "RAGStore | None" = None,  # type: ignore
    ):
        """
        Initialize RAGQuery.

        Args:
            db_path: Path to ChromaDB database (ignored if store is provided)
            collection_name: Name of the collection (ignored if store is provided)
            store: Optional RAGStore to share collection with (preferred)
        """
        self._store = store
        if store is not None:
            # Use store's client, access collection dynamically via property
            self._client = store._client
            self.db_path = store.db_path
            self.collection_name = store.collection_name
        else:
            # Create own client (for backwards compatibility)
            self._store = None
            self.db_path = Path(db_path) if db_path else Path("./chroma_db")
            self.collection_name = collection_name
            self._client = chromadb.PersistentClient(
                path=str(self.db_path),
                settings=Settings(anonymized_telemetry=False),
            )
            self._own_collection = self._client.get_or_create_collection(collection_name)

    @property
    def _collection(self):
        """Get collection - delegates to store if available for consistency after clear()."""
        if self._store is not None:
            return self._store._collection
        return self._own_collection

    def search(
        self,
        query: str,
        n_results: int = 5,
        where: dict | None = None,
    ) -> list[QueryResult]:
        """
        Search for relevant chunks.

        Args:
            query: Natural language query
            n_results: Maximum number of results
            where: Optional filter conditions

        Returns:
            List of QueryResult objects, ordered by relevance
        """
        results = self._collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        query_results = []
        for i, chunk_id in enumerate(results["ids"][0]):
            chunk = Chunk(
                id=chunk_id,
                content=results["documents"][0][i],
                metadata=ChunkMetadata.from_chroma_format(results["metadatas"][0][i]),
            )
            score = results["distances"][0][i] if results.get("distances") else 0.0
            query_results.append(QueryResult(chunk=chunk, score=score))

        return query_results

    def search_by_type(
        self,
        query: str,
        chunk_type: str,
        n_results: int = 5,
    ) -> list[QueryResult]:
        """Search for chunks of a specific type."""
        return self.search(
            query=query,
            n_results=n_results,
            where={"type": chunk_type},
        )

    def search_by_path(
        self,
        query: str,
        path_pattern: str,
        n_results: int = 5,
    ) -> list[QueryResult]:
        """Search within files matching a path pattern."""
        return self.search(
            query=query,
            n_results=n_results,
            where={"path": {"$contains": path_pattern}},
        )

    def get_related(
        self,
        chunk_id: str,
        n_results: int = 5,
    ) -> list[QueryResult]:
        """Get chunks related to a given chunk (by content similarity)."""
        # Get the chunk content first
        result = self._collection.get(ids=[chunk_id])

        if not result["ids"]:
            return []

        content = result["documents"][0]

        # Search for similar content, excluding the original
        results = self._collection.query(
            query_texts=[content],
            n_results=n_results + 1,  # Extra to account for self-match
        )

        query_results = []
        for i, cid in enumerate(results["ids"][0]):
            if cid == chunk_id:
                continue  # Skip self-match

            chunk = Chunk(
                id=cid,
                content=results["documents"][0][i],
                metadata=ChunkMetadata.from_chroma_format(results["metadatas"][0][i]),
            )
            score = results["distances"][0][i] if results.get("distances") else 0.0
            query_results.append(QueryResult(chunk=chunk, score=score))

            if len(query_results) >= n_results:
                break

        return query_results

    def get_context_for_query(
        self,
        query: str,
        max_tokens: int = 8000,
        n_results: int = 20,
    ) -> str:
        """
        Get formatted context string for LLM consumption.

        Retrieves relevant chunks and formats them for context.
        Respects approximate token budget.
        """
        results = self.search(query, n_results=n_results)

        context_parts = []
        approx_tokens = 0

        for result in results:
            chunk = result.chunk
            # Rough token estimate: ~4 chars per token
            chunk_tokens = len(chunk.content) // 4

            if approx_tokens + chunk_tokens > max_tokens:
                break

            # Format chunk for context
            header = f"[{chunk.metadata.chunk_type}] {chunk.metadata.path}"
            if chunk.metadata.signature:
                header += f" - {chunk.metadata.signature}"

            context_parts.append(f"{header}\n{chunk.content}")
            approx_tokens += chunk_tokens

        return "\n\n---\n\n".join(context_parts)
