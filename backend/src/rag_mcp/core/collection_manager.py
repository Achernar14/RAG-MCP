"""Collection manager — scoped data isolation for multi-collection support.

Each named collection owns an independent set of vector store, document
repository, chunk repository, and BM25 sparse index.  Operations targeting
different collections are fully isolated.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rag_mcp.core.exceptions import CollectionNameError
from rag_mcp.infrastructure.repositories.json_repositories import (
    JsonChunkRepository,
    JsonDocumentRepository,
)
from rag_mcp.infrastructure.sparse.sqlite_fts_store import SqliteFtsStore

if TYPE_CHECKING:
    from rag_mcp.core.settings import Settings
    from rag_mcp.infrastructure.vector_store.chroma_store import ChromaVectorStore
    from rag_mcp.infrastructure.vector_store.memory_store import InMemoryVectorStore
    from rag_mcp.infrastructure.vector_store.weaviate_store import WeaviateVectorStore

logger = logging.getLogger(__name__)

# ── collection name validation ─────────────────────────────────────────

# Allowed characters: alphanumeric, underscore, hyphen, dot.
# Dots are permitted for compound names (e.g. "rag_mcp_live") but a lone
# "." or ".." is rejected separately.
_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9_.-]*$")

# Maximum length for a collection name — keeps directory names reasonable
# and avoids filesystem limits (most systems cap single path components
# at 255 bytes).
_MAX_NAME_LENGTH = 64

# Windows reserved file names — these cannot be used as directory names
# regardless of extension.
_WINDOWS_RESERVED_NAMES: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5",
    "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5",
    "LPT6", "LPT7", "LPT8", "LPT9",
})


def validate_collection_name(name: str) -> str:
    """Validate *name* and return it (normalised) on success.

    Raises :class:`CollectionNameError` when the name is invalid.

    Rules enforced:
    * Non-empty, max 64 characters
    * Starts with an alphanumeric character or underscore
    * Contains only ``[a-zA-Z0-9_.-]``
    * Not ``.`` or ``..`` (path traversal)
    * Not a Windows reserved name (``CON``, ``NUL``, ``COM1``, …)
    """
    if not name:
        raise CollectionNameError("Collection name must not be empty.")
    if len(name) > _MAX_NAME_LENGTH:
        raise CollectionNameError(
            f"Collection name must be ≤ {_MAX_NAME_LENGTH} characters "
            f"(got {len(name)})."
        )
    if name in (".", ".."):
        raise CollectionNameError(
            f"Collection name must not be '{name}' (path traversal)."
        )

    if not _VALID_NAME_RE.match(name):
        raise CollectionNameError(
            f"Invalid collection name '{name}'. "
            f"Allowed characters: a-z, A-Z, 0-9, underscore, hyphen, dot. "
            f"Must start with a letter, digit, or underscore."
        )

    upper = name.upper()
    # Strip trailing dots + extension-like suffixes for reserved-name
    # detection: "NUL." and "NUL.foo" are also inaccessible on Windows.
    base = upper.split(".")[0]
    if base in _WINDOWS_RESERVED_NAMES or upper in _WINDOWS_RESERVED_NAMES:
        raise CollectionNameError(
            f"Collection name '{name}' is a reserved system name on Windows."
        )

    return name


@dataclass
class CollectionScope:
    """All data stores for a single logical collection."""

    name: str
    vector_store: VectorStore
    document_repository: JsonDocumentRepository
    chunk_repository: JsonChunkRepository
    sparse_index: SqliteFtsStore


class CollectionManager:
    """Create and cache :class:`CollectionScope` instances by name.

    Each scope uses a dedicated subdirectory under the vector-store root::

        {root_dir}/
          {collection_name}/
            chroma_live/     (or ``weaviate/``)
            documents.json
            chunks.json
            bm25_index.json
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._scopes: dict[str, CollectionScope] = {}
        vs = settings.vector_store
        self._provider = vs.provider.lower()
        self._root = self._resolve_root(vs)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def get_scope(self, collection_name: str | None = None) -> CollectionScope:
        """Return (possibly creating) the scope for *collection_name*.

        When *collection_name* is ``None`` the configured default is used.
        """
        name = collection_name or self._settings.vector_store.collection_name
        # Validate before touching the filesystem — prevents path traversal
        # and other malicious directory names.
        validate_collection_name(name)
        if name not in self._scopes:
            self._scopes[name] = self._build_scope(name)
        return self._scopes[name]

    @property
    def default_scope(self) -> CollectionScope:
        """The scope for the default collection from settings."""
        return self.get_scope()

    def list_collections(self) -> list[str]:
        """Return names of collections that exist on disk.

        Only directories containing a ``documents.json`` file are recognised.
        """
        if not self._root.exists():
            return []
        names: list[str] = []
        for child in sorted(self._root.iterdir()):
            if child.is_dir() and (child / "documents.json").exists():
                names.append(child.name)
        # Ensure configured default is always present
        default = self._settings.vector_store.collection_name
        if default not in names:
            # Create the default scope so it shows up
            self.get_scope(default)
            if (self._root / default / "documents.json").exists():
                names.append(default)
        return names or [default]

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a collection and its persisted data.

        Returns ``False`` if the collection did not exist.
        """
        scope = self._scopes.pop(collection_name, None)
        if scope is None and not (self._root / collection_name).exists():
            return False
        if scope is not None:
            close_fn = getattr(scope.vector_store, "close", None)
            if callable(close_fn):
                close_fn()
        # Remove persisted files
        import shutil
        collection_dir = self._root / collection_name
        if collection_dir.exists():
            shutil.rmtree(collection_dir, ignore_errors=True)
        return True

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------

    def _resolve_root(self, vs) -> Path:
        """Determine the parent directory for per-collection subdirectories."""
        from rag_mcp.core.settings import resolve_project_path

        if self._provider == "weaviate":
            return resolve_project_path(vs.weaviate_persistence_data_path).parent
        return resolve_project_path(vs.persist_path).parent

    def _build_scope(self, name: str) -> CollectionScope:
        """Create all data stores for a named collection."""
        collection_dir = self._root / name
        collection_dir.mkdir(parents=True, exist_ok=True)

        document_repo = JsonDocumentRepository(collection_dir / "documents.json")
        chunk_repo = JsonChunkRepository(collection_dir / "chunks.json")
        sparse_index = SqliteFtsStore(collection_dir / "bm25_fts.db")
        vector_store = self._build_vector_store(name, collection_dir)

        return CollectionScope(
            name=name,
            vector_store=vector_store,
            document_repository=document_repo,
            chunk_repository=chunk_repo,
            sparse_index=sparse_index,
        )

    def _build_vector_store(self, name: str, collection_dir: Path) -> VectorStore:
        """Create the appropriate vector store instance for this collection."""
        vs = self._settings.vector_store

        if self._provider == "memory":
            from rag_mcp.infrastructure.vector_store.memory_store import InMemoryVectorStore
            return InMemoryVectorStore()

        if self._provider == "chroma":
            from rag_mcp.infrastructure.vector_store.chroma_store import ChromaVectorStore
            persist_path = str(collection_dir / "chroma_live")
            return ChromaVectorStore(
                persist_path=persist_path,
                collection_name=name,
            )

        if self._provider == "weaviate":
            from rag_mcp.infrastructure.vector_store.weaviate_store import WeaviateVectorStore
            from rag_mcp.core.settings import resolve_project_path
            return WeaviateVectorStore(
                mode=vs.weaviate_mode,
                persistence_data_path=str(collection_dir / "weaviate"),
                version=vs.weaviate_version,
                hostname=vs.weaviate_hostname,
                port=vs.weaviate_port,
                grpc_port=vs.weaviate_grpc_port,
                api_key=vs.weaviate_api_key,
                collection_name=name,
            )

        raise ValueError(f"Unsupported vector store provider: {self._provider}")
