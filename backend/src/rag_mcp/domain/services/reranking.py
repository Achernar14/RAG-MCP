"""Reranking primitives."""

from __future__ import annotations

from abc import ABC, abstractmethod

from rag_mcp.domain.entities.models import RetrievalResult


class BaseReranker(ABC):
    """Contract for reranking a recalled result set."""

    @abstractmethod
    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        """Return reranked results."""
