"""Repository and provider contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from rag_mcp.domain.entities.models import (
    Chunk,
    ChunkRecord,
    Document,
    EvaluationReport,
    RetrievalResult,
)


class EmbeddingProvider(ABC):
    """Embedding provider contract."""

    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return dense vectors for texts."""


class LlmProvider(ABC):
    """LLM generation provider contract."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Generate a completion from a prompt."""

    @abstractmethod
    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> Iterator[str]:
        """Stream completion tokens as an iterator of delta strings."""


class DocumentRepository(ABC):
    """Document repository contract."""

    @abstractmethod
    def save(self, document: Document) -> None:
        """Persist a document."""

    @abstractmethod
    def list_all(self) -> list[Document]:
        """Return all documents."""

    @abstractmethod
    def get(self, document_id: str) -> Document | None:
        """Return a document if present."""

    @abstractmethod
    def get_by_source_path(self, source_path: str) -> Document | None:
        """Return a document by normalized source path if present."""

    @abstractmethod
    def delete(self, document_id: str) -> bool:
        """Delete a document and return whether it existed."""


class ChunkRepository(ABC):
    """Chunk repository contract."""

    @abstractmethod
    def save_many(self, chunks: list[Chunk]) -> None:
        """Persist chunks."""

    @abstractmethod
    def list_by_document(self, document_id: str) -> list[Chunk]:
        """List chunks by document."""

    @abstractmethod
    def delete_by_document(self, document_id: str) -> int:
        """Delete chunks for a document and return the deleted count."""


class VectorStoreRepository(ABC):
    """Vector storage contract."""

    @abstractmethod
    def upsert(self, records: list[ChunkRecord]) -> None:
        """Upsert chunk records."""

    @abstractmethod
    def query(self, query_vector: list[float], top_k: int) -> list[RetrievalResult]:
        """Return top-k retrieval results."""

    @abstractmethod
    def delete_by_document(self, document_id: str) -> int:
        """Delete all vectors for a document and return the deleted count."""


class SparseIndexRepository(ABC):
    """Sparse retrieval contract."""

    @abstractmethod
    def upsert(self, records: list[ChunkRecord]) -> None:
        """Update the sparse index with chunk records."""

    @abstractmethod
    def query(self, query_text: str, top_k: int) -> list[RetrievalResult]:
        """Return top-k sparse retrieval results."""

    @abstractmethod
    def delete_by_document(self, document_id: str) -> int:
        """Delete sparse index entries for a document and return the deleted count."""


class EvaluationReportRepository(ABC):
    """Evaluation report persistence contract."""

    @abstractmethod
    def save(self, report: EvaluationReport) -> None:
        """Persist an evaluation report."""

    @abstractmethod
    def list_reports(self, limit: int = 20) -> list[EvaluationReport]:
        """List recent evaluation reports."""

    @abstractmethod
    def get(self, report_id: str) -> EvaluationReport | None:
        """Return a report by id if present."""
