"""Dense retrieval service."""

from __future__ import annotations

import time


class RetrievalService:
    """Perform dense retrieval against the configured vector store."""

    def __init__(self, embedding_provider, vector_store) -> None:
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def search(self, query: str, top_k: int, trace) -> list:
        """Embed the query and return the top-k matches."""
        start = time.monotonic()
        query_vector = self.embedding_provider.embed_texts([query])[0]
        trace.record_stage(
            "embed_query",
            {"provider": self.embedding_provider.__class__.__name__},
            (time.monotonic() - start) * 1000.0,
        )

        start = time.monotonic()
        results = self.vector_store.query(query_vector=query_vector, top_k=top_k)
        trace.record_stage(
            "dense_retrieval",
            {"result_count": len(results)},
            (time.monotonic() - start) * 1000.0,
        )
        return results

