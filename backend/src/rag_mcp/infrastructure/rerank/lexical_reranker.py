"""A lightweight lexical reranker for local development."""

from __future__ import annotations

import re

from rag_mcp.domain.entities.models import RetrievalResult
from rag_mcp.domain.services.reranking import BaseReranker


TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


class LexicalReranker(BaseReranker):
    """Boost results by token overlap between query and chunk text."""

    def rerank(self, query: str, results: list[RetrievalResult], top_k: int) -> list[RetrievalResult]:
        """Rerank results using lexical overlap and original score."""
        query_terms = {token.lower() for token in TOKEN_PATTERN.findall(query)}
        scored: list[tuple[float, RetrievalResult]] = []
        for result in results:
            result_terms = {token.lower() for token in TOKEN_PATTERN.findall(result.text)}
            overlap = len(query_terms & result_terms)
            rerank_score = overlap * 10.0 + result.score
            scored.append((rerank_score, result))

        scored.sort(key=lambda item: item[0], reverse=True)
        top_score = scored[0][0] if scored else 1.0
        reranked: list[RetrievalResult] = []
        for score, result in scored[:top_k]:
            reranked.append(
                RetrievalResult(
                    chunk_id=result.chunk_id,
                    score=score / max(top_score, 1e-9),
                    text=result.text,
                    metadata=result.metadata,
                    retrieval_method=self._extend_method(result.retrieval_method),
                )
            )
        return reranked

    def _extend_method(self, retrieval_method: str | None) -> str:
        if not retrieval_method:
            return "rerank"
        if "rerank" in retrieval_method:
            return retrieval_method
        return f"{retrieval_method}+rerank"
