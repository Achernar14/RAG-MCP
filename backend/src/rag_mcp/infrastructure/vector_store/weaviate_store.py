"""Weaviate Embedded vector store implementation.

Runs Weaviate in-process via the Python client — no Docker, no external service.
"""

from __future__ import annotations

from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.embedded import EmbeddedOptions

from rag_mcp.core.exceptions import ProviderError
from rag_mcp.domain.entities.models import ChunkRecord, RetrievalResult


class WeaviateVectorStore:
    """Persist embeddings and metadata in Weaviate Embedded."""

    _SCHEMA = [
        Property(name="text", data_type=DataType.TEXT),
        Property(name="document_id", data_type=DataType.TEXT),
        Property(name="chunk_index", data_type=DataType.INT),
    ]

    def __init__(
        self,
        *,
        persistence_data_path: str,
        version: str = "1.37.2",
        hostname: str = "127.0.0.1",
        port: int = 8079,
        collection_name: str = "RAG_MCP",
    ) -> None:
        self.collection_name = collection_name

        data_dir = Path(persistence_data_path)
        data_dir.mkdir(parents=True, exist_ok=True)

        embedded_opts = EmbeddedOptions(
            persistence_data_path=str(data_dir),
            version=version,
            hostname=hostname,
            port=port,
            additional_env_vars={"LOG_LEVEL": "error"},
        )

        try:
            self.client = weaviate.WeaviateClient(
                embedded_options=embedded_opts,
            )
            self.client.connect()
        except Exception as exc:
            raise ProviderError(f"Weaviate Embedded 启动失败: {exc}") from exc

        self._ensure_collection()

    # ------------------------------------------------------------------
    # Public interface (duck-typed with ChromaVectorStore)
    # ------------------------------------------------------------------

    def upsert(self, records: list[ChunkRecord]) -> None:
        if not records:
            return
        collection = self.client.collections.use(self.collection_name)
        with collection.batch.fixed_size(batch_size=200) as batch:
            for record in records:
                batch.add_object(
                    properties={
                        "text": record.text,
                        "document_id": record.metadata.get("document_id", ""),
                        "chunk_index": record.metadata.get("chunk_index", 0),
                    },
                    vector=record.dense_vector,
                    uuid=self._record_uuid(record.id),
                )
        if collection.batch.failed_objects:
            failed = collection.batch.failed_objects
            raise ProviderError(
                f"Weaviate batch upsert: {len(failed)} failures, "
                f"first: {failed[0].message}"
            )

    def query(self, query_vector: list[float], top_k: int) -> list[RetrievalResult]:
        collection = self.client.collections.use(self.collection_name)
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=top_k,
            return_metadata=MetadataQuery(distance=True),
        )
        results: list[RetrievalResult] = []
        for obj in response.objects:
            results.append(RetrievalResult(
                chunk_id=str(obj.uuid),
                score=self._distance_to_score(obj.metadata.distance),
                text=obj.properties.get("text", ""),
                metadata={
                    "document_id": obj.properties.get("document_id", ""),
                    "chunk_index": obj.properties.get("chunk_index", 0),
                },
            ))
        return results

    def delete_by_document(self, document_id: str) -> int:
        collection = self.client.collections.use(self.collection_name)
        result = collection.data.delete_many(
            where=Filter.by_property("document_id").equal(document_id),
        )
        return result.successful

    def close(self) -> None:
        self.client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        if not self.client.collections.exists(self.collection_name):
            self.client.collections.create(
                name=self.collection_name,
                vector_config=Configure.Vectors.self_provided(
                    vector_index_config=Configure.VectorIndex.hnsw(
                        distance_metric=VectorDistances.COSINE,
                    ),
                ),
                properties=self._SCHEMA,
            )

    @staticmethod
    def _record_uuid(chunk_id: str) -> str:
        return str(uuid5(NAMESPACE_DNS, chunk_id))

    @staticmethod
    def _distance_to_score(distance: float | None) -> float:
        if distance is None:
            return 0.0
        return 1.0 - distance
