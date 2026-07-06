"""Weaviate vector store — dual-mode: embedded (in-process) and remote (external).

- ``embedded``: Runs Weaviate in-process via EmbeddedOptions (Linux/macOS only).
- ``remote``: Connects to an external Weaviate instance (Docker container or
  Weaviate Cloud). Cross-platform (including Windows).
"""

from __future__ import annotations

from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import Filter, MetadataQuery

from rag_mcp.core.exceptions import ConfigurationError, ProviderError
from rag_mcp.domain.entities.models import ChunkRecord, RetrievalResult


class WeaviateVectorStore:
    """Persist embeddings and metadata in Weaviate.

    Supports two connection modes driven by the ``mode`` parameter:

    - ``"embedded"`` — uses ``weaviate.embedded.EmbeddedOptions`` (default,
      Linux/macOS only; does **not** work on Windows).
    - ``"remote"`` — uses ``weaviate.connect_to_local()`` to reach a
      Docker-hosted or cloud Weaviate.  Works on all platforms.
    """

    _SCHEMA = [
        Property(name="text", data_type=DataType.TEXT),
        Property(name="document_id", data_type=DataType.TEXT),
        Property(name="chunk_index", data_type=DataType.INT),
    ]

    _EMBEDDED = "embedded"
    _REMOTE = "remote"

    def __init__(
        self,
        *,
        mode: str = "embedded",
        persistence_data_path: str | None = None,
        version: str = "1.37.2",
        hostname: str = "127.0.0.1",
        port: int = 8079,
        grpc_port: int = 50051,
        api_key: str | None = None,
        collection_name: str = "RAG_MCP",
    ) -> None:
        self.collection_name = collection_name

        if mode not in (self._EMBEDDED, self._REMOTE):
            raise ConfigurationError(
                f"Invalid weaviate_mode: {mode!r}. Use {self._EMBEDDED!r} or {self._REMOTE!r}."
            )

        if mode == self._EMBEDDED:
            self._connect_embedded(
                persistence_data_path=persistence_data_path,
                version=version,
                hostname=hostname,
                port=port,
            )
        else:
            self._connect_remote(
                hostname=hostname,
                port=port,
                grpc_port=grpc_port,
                api_key=api_key,
            )

        self._ensure_collection()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect_embedded(
        self,
        persistence_data_path: str | None,
        version: str,
        hostname: str,
        port: int,
    ) -> None:
        """Connect using Weaviate Embedded (in-process, Linux/macOS only)."""
        from weaviate.embedded import EmbeddedOptions

        data_dir = Path(persistence_data_path or "data/vector_store/weaviate")
        data_dir.mkdir(parents=True, exist_ok=True)

        embedded_opts = EmbeddedOptions(
            persistence_data_path=str(data_dir),
            version=version,
            hostname=hostname,
            port=port,
            additional_env_vars={"LOG_LEVEL": "error"},
        )

        try:
            self.client = weaviate.WeaviateClient(embedded_options=embedded_opts)
            self.client.connect()
        except Exception as exc:
            raise ProviderError(f"Weaviate Embedded 启动失败: {exc}") from exc

    def _connect_remote(
        self,
        hostname: str,
        port: int,
        grpc_port: int,
        api_key: str | None,
    ) -> None:
        """Connect to an external Weaviate instance (Docker / Cloud)."""
        additional_headers = {}
        if api_key:
            additional_headers["X-API-Key"] = api_key

        try:
            self.client = weaviate.connect_to_local(
                host=hostname,
                port=port,
                grpc_port=grpc_port,
                headers=additional_headers if additional_headers else None,
            )
        except Exception as exc:
            raise ProviderError(
                f"Weaviate Remote 连接失败 ({hostname}:{port}, "
                f"grpc={grpc_port}): {exc}"
            ) from exc

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
