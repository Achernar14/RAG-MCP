"""A deterministic local embedding provider for MVP development."""

from __future__ import annotations

import hashlib


class HashEmbeddingProvider:
    """Generate deterministic fixed-size vectors from text."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Convert texts into deterministic dense vectors."""
        return [self._embed_single(text) for text in texts]

    def _embed_single(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector = [0.0] * self.dimensions
        for index in range(self.dimensions):
            byte_value = digest[index % len(digest)]
            vector[index] = byte_value / 255.0
        return vector

