"""ChromaDB-based vector store for code semantics."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

import chromadb
from chromadb.config import Settings


@dataclass
class ChunkMetadata:
    """Metadata for a stored chunk."""

    path: str = ""
    language: str = ""
    chunk_type: str = ""  # file, function, class, etc.
    concepts: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)
    signature: str = ""
    extra: dict = field(default_factory=dict)

    def to_chroma_format(self) -> dict[str, Any]:
        """Convert to ChromaDB-compatible format (no lists)."""
        return {
            "path": self.path,
            "language": self.language,
            "type": self.chunk_type,
            "concepts": ", ".join(self.concepts) if self.concepts else "",
            "calls": ", ".join(self.calls) if self.calls else "",
            "called_by": ", ".join(self.called_by) if self.called_by else "",
            "signature": self.signature,
            "extra": json.dumps(self.extra) if self.extra else "",
        }

    @classmethod
    def from_chroma_format(cls, data: dict[str, Any]) -> "ChunkMetadata":
        """Create from ChromaDB metadata format."""
        return cls(
            path=data.get("path", ""),
            language=data.get("language", ""),
            chunk_type=data.get("type", ""),
            concepts=[c.strip() for c in data.get("concepts", "").split(",") if c.strip()],
            calls=[c.strip() for c in data.get("calls", "").split(",") if c.strip()],
            called_by=[c.strip() for c in data.get("called_by", "").split(",") if c.strip()],
            signature=data.get("signature", ""),
            extra=json.loads(data.get("extra", "{}")) if data.get("extra") else {},
        )


@dataclass
class Chunk:
    """A chunk of code or documentation."""

    id: str
    content: str
    metadata: ChunkMetadata


class RAGStore:
    """ChromaDB-based vector store for semantic code search."""

    def __init__(
        self,
        db_path: Path | str = "./chroma_db",
        collection_name: str = "codebase_specs",
    ):
        self.db_path = Path(db_path)
        self.collection_name = collection_name

        self._client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(collection_name)

    def add(self, chunk: Chunk) -> None:
        """Add a single chunk to the store."""
        self._collection.add(
            ids=[chunk.id],
            documents=[chunk.content],
            metadatas=[chunk.metadata.to_chroma_format()],
        )

    def add_batch(self, chunks: list[Chunk]) -> None:
        """Add multiple chunks efficiently."""
        if not chunks:
            return

        self._collection.add(
            ids=[c.id for c in chunks],
            documents=[c.content for c in chunks],
            metadatas=[c.metadata.to_chroma_format() for c in chunks],
        )

    def get(self, chunk_id: str) -> Chunk | None:
        """Get a chunk by ID."""
        result = self._collection.get(ids=[chunk_id])

        if not result["ids"]:
            return None

        return Chunk(
            id=result["ids"][0],
            content=result["documents"][0],
            metadata=ChunkMetadata.from_chroma_format(result["metadatas"][0]),
        )

    def delete(self, chunk_id: str) -> None:
        """Delete a chunk by ID."""
        self._collection.delete(ids=[chunk_id])

    def delete_by_path(self, path: str) -> int:
        """Delete all chunks for a given file path."""
        # Get matching IDs first
        result = self._collection.get(
            where={"path": path},
        )

        if result["ids"]:
            self._collection.delete(ids=result["ids"])
            return len(result["ids"])

        return 0

    def count(self) -> int:
        """Get total number of chunks in store."""
        return self._collection.count()

    def clear(self) -> None:
        """Clear all chunks from the store."""
        # Delete and recreate collection
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(self.collection_name)

    def load_from_json(self, json_path: Path | str) -> int:
        """
        Load chunks from a JSON spec file.

        Expected format:
        {
            "file_chunks": [...],
            "code_unit_chunks": [...]
        }

        Returns number of chunks loaded.
        """
        with open(json_path) as f:
            spec = json.load(f)

        chunks = []

        # Process file chunks
        for chunk_data in spec.get("file_chunks", []):
            metadata = chunk_data.get("metadata", {})
            chunks.append(
                Chunk(
                    id=chunk_data["id"],
                    content=chunk_data["content"],
                    metadata=ChunkMetadata(
                        path=metadata.get("path", ""),
                        language=metadata.get("language", ""),
                        chunk_type="file",
                        concepts=metadata.get("concepts", []),
                    ),
                )
            )

        # Process code unit chunks
        for chunk_data in spec.get("code_unit_chunks", []):
            metadata = chunk_data.get("metadata", {})
            chunks.append(
                Chunk(
                    id=chunk_data["id"],
                    content=chunk_data["content"],
                    metadata=ChunkMetadata(
                        path=metadata.get("file", ""),
                        chunk_type=metadata.get("type", "function"),
                        signature=metadata.get("signature", ""),
                        calls=metadata.get("calls", []),
                        called_by=metadata.get("called_by", []),
                    ),
                )
            )

        self.add_batch(chunks)
        return len(chunks)
