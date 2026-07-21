"""Cross-Encoder reranker using sentence-transformers.

Uses BAAI/bge-reranker-v2-m3 by default — a multilingual model that
covers Chinese and English, matching the project's primary use case.
"""

from __future__ import annotations

import logging

from rag_mcp.domain.entities.models import RetrievalResult
from rag_mcp.domain.services.reranking import BaseReranker

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"


class CrossEncoderReranker(BaseReranker):
    """Semantic reranker backed by a sentence-transformers CrossEncoder.

    On first use the model is downloaded from HuggingFace Hub and cached
    in ``~/.cache/huggingface/`` (~2.3 GB for the default model).  GPU
    acceleration is used automatically when available.
    """

    def __init__(self, model_name: str | None = None, max_length: int = 512) -> None:
        from sentence_transformers import CrossEncoder  # lazy — optional dependency

        _model = model_name or _DEFAULT_MODEL
        logger.info("Loading cross-encoder model %s (this may take a moment on first run) ...", _model)
        self.model = CrossEncoder(_model, max_length=max_length)
        logger.info("Cross-encoder model %s loaded.", _model)

    def rerank(
        self, query: str, results: list[RetrievalResult], top_k: int
    ) -> list[RetrievalResult]:
        if not results:
            return []

        pairs = [[query, r.text] for r in results]
        scores = self.model.predict(pairs, show_progress_bar=False)

        ranked = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)
        return [
            RetrievalResult(
                chunk_id=r.chunk_id,
                score=float(score),
                text=r.text,
                metadata=r.metadata,
                retrieval_method=self._extend_method(r.retrieval_method),
            )
            for r, score in ranked[:top_k]
        ]

    @staticmethod
    def _extend_method(method: str | None) -> str:
        label = "cross_encoder"
        if not method:
            return label
        if label in method:
            return method
        return f"{method}+{label}"
