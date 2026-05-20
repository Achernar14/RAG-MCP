"""Hybrid retrieval service with dense + sparse + RRF fusion."""

from __future__ import annotations

import time

from rag_mcp.domain.entities.models import RetrievalResult


class HybridRetrievalService:
    """Combine dense and sparse retrieval using Reciprocal Rank Fusion."""

    def __init__(self, embedding_provider, vector_store, sparse_index, settings, reranker=None) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.sparse_index = sparse_index
        self.settings = settings
        self.reranker = reranker

    def search(self, query: str, top_k: int, trace) -> list[RetrievalResult]:
        """Execute dense and sparse retrieval, then fuse results."""
        start = time.monotonic()
        query_vector = self.embedding_provider.embed_texts([query])[0]
        trace.record_stage(
            "embed_query",
            {"provider": self.embedding_provider.__class__.__name__},
            (time.monotonic() - start) * 1000.0,
        )

        start = time.monotonic()
        dense_results = self.vector_store.query(
            query_vector=query_vector,
            top_k=self.settings.dense_top_k,
        )
        for result in dense_results:
            result.retrieval_method = "dense"
        trace.record_stage(
            "dense_retrieval",
            {"result_count": len(dense_results)},
            (time.monotonic() - start) * 1000.0,
        )

        start = time.monotonic()
        sparse_results = self.sparse_index.query(
            query_text=query,
            top_k=self.settings.sparse_top_k,
        )
        trace.record_stage(
            "sparse_retrieval",
            {"result_count": len(sparse_results)},
            (time.monotonic() - start) * 1000.0,
        )

        start = time.monotonic()
        fused = self._rrf_fuse(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_k=min(top_k, self.settings.hybrid_top_k),
            rrf_k=self.settings.rrf_k,
        )
        trace.record_stage(
            "fusion",
            {"result_count": len(fused), "method": "rrf"},
            (time.monotonic() - start) * 1000.0,
        )
        if self.settings.rerank_enabled and self.reranker is not None and fused:
            start = time.monotonic()
            reranked = self.reranker.rerank(
                query=query,
                results=fused,
                top_k=min(top_k, self.settings.rerank_top_k),
            )
            trace.record_stage(
                "rerank",
                {"result_count": len(reranked), "method": self.reranker.__class__.__name__},
                (time.monotonic() - start) * 1000.0,
            )
            return reranked
        return fused

    def _rrf_fuse(
        self,
        dense_results: list[RetrievalResult],
        sparse_results: list[RetrievalResult],
        top_k: int,
        rrf_k: int,
    ) -> list[RetrievalResult]:
        """Fuse ranked lists with Reciprocal Rank Fusion."""
        aggregated: dict[str, dict] = {}
        for label, results in (("dense", dense_results), ("sparse", sparse_results)):
            for rank, result in enumerate(results, start=1):
                payload = aggregated.setdefault(
                    result.chunk_id,
                    {
                        "result": result,
                        "score": 0.0,
                        "methods": set(),
                    },
                )
                payload["score"] += 1.0 / (rrf_k + rank)
                payload["methods"].add(label)

        fused: list[RetrievalResult] = []
        ordered = sorted(
            aggregated.values(),
            key=lambda item: item["score"],
            reverse=True,
        )
        max_score = ordered[0]["score"] if ordered else 1.0
        for item in ordered[:top_k]:
            result = item["result"]
            fused.append(
                RetrievalResult(
                    chunk_id=result.chunk_id,
                    score=item["score"] / max(max_score, 1e-9),
                    text=result.text,
                    metadata=result.metadata,
                    retrieval_method="+".join(sorted(item["methods"])),
                )
            )
        return fused
