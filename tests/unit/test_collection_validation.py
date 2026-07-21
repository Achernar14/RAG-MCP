"""Unit tests for collection name validation and path traversal prevention."""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.core.collection_manager import validate_collection_name
from rag_mcp.factory import reset_container
from rag_mcp.core.exceptions import CollectionNameError
from rag_mcp.main import create_app


# ── validate_collection_name unit tests ────────────────────────────────


class TestValidNames:
    """Names that should pass validation."""

    @pytest.mark.parametrize("name", [
        "default",
        "rag_mcp_live",
        "my-collection",
        "project.v1",
        "test_123",
        "a",                          # single char
        "A" * 64,                     # exactly max length
        "_internal",                  # starts with underscore
        "my.collection.name-v2",     # compound with dots and hyphens
        "ABC_def-123.456",           # mixed case
    ])
    def test_valid_name_passes(self, name: str):
        result = validate_collection_name(name)
        assert result == name


class TestEmptyAndLength:
    """Empty and over-long names."""

    def test_empty_string_rejected(self):
        with pytest.raises(CollectionNameError, match="must not be empty"):
            validate_collection_name("")

    def test_too_long_rejected(self):
        name = "x" * 65
        with pytest.raises(CollectionNameError, match="≤ 64"):
            validate_collection_name(name)

    def test_exactly_max_length_passes(self):
        name = "A" * 64
        assert validate_collection_name(name) == name


class TestPathTraversal:
    """Names that attempt path traversal are rejected."""

    @pytest.mark.parametrize("name,desc", [
        (".", "single dot"),
        ("..", "double dot"),
        ("../etc", "parent dir with path"),
        ("..\\Windows", "parent dir with backslash"),
        ("foo/bar", "forward slash"),
        ("foo\\bar", "backslash"),
        ("../../etc/passwd", "deep traversal forward"),
        ("..\\..\\Windows\\System32", "deep traversal backward"),
        ("foo/", "trailing forward slash"),
        ("foo\\", "trailing backslash"),
        ("/etc", "leading forward slash"),
        ("\\Windows", "leading backslash"),
    ])
    def test_path_traversal_rejected(self, name: str, desc: str):
        with pytest.raises(CollectionNameError):
            validate_collection_name(name)


class TestWindowsReservedNames:
    """Windows reserved file names are rejected."""

    @pytest.mark.parametrize("name", [
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5",
        "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5",
        "LPT6", "LPT7", "LPT8", "LPT9",
    ])
    def test_reserved_name_rejected(self, name: str):
        with pytest.raises(CollectionNameError, match="reserved"):
            validate_collection_name(name)

    @pytest.mark.parametrize("name", [
        "con", "nul", "prn", "aux",          # lowercase
        "Con", "Nul", "Prn", "Aux",          # mixed case
        "com1", "lpt1",                       # lowercase variants
    ])
    def test_reserved_name_case_insensitive(self, name: str):
        with pytest.raises(CollectionNameError, match="reserved"):
            validate_collection_name(name)

    @pytest.mark.parametrize("name", [
        "NUL.txt", "CON.foo", "COM1.bar",
        "nul.data", "prn.json", "lpt1.backup",
    ])
    def test_reserved_name_with_extension_rejected(self, name: str):
        """NUL.txt, CON.foo etc. are also blocked on Windows."""
        with pytest.raises(CollectionNameError, match="reserved"):
            validate_collection_name(name)


class TestInvalidCharacters:
    """Names with characters outside the allowed set."""

    @pytest.mark.parametrize("name,desc", [
        ("foo bar", "space"),
        ("foo\tbar", "tab"),
        ("foo\nbar", "newline"),
        ("foo@bar", "at sign"),
        ("foo!bar", "exclamation"),
        ("foo#bar", "hash"),
        ("foo$bar", "dollar"),
        ("foo%bar", "percent"),
        ("foo^bar", "caret"),
        ("foo&bar", "ampersand"),
        ("foo*bar", "asterisk"),
        ("foo(bar", "parenthesis"),
        ("foo=bar", "equals"),
        ("foo+bar", "plus"),
        ("foo{bar", "brace"),
        ("foo[bar", "bracket"),
        ("foo|bar", "pipe"),
        ("foo:bar", "colon"),
        ("foo;bar", "semicolon"),
        ("foo'bar", "single quote"),
        ('foo"bar', "double quote"),
        ("foo<bar", "angle bracket"),
        ("foo>bar", "greater than"),
        ("foo?bar", "question mark"),
        ("foo`bar", "backtick"),
        ("foo~bar", "tilde"),
        ("你好", "CJK characters"),
    ])
    def test_invalid_characters_rejected(self, name: str, desc: str):
        with pytest.raises(CollectionNameError, match="Invalid collection name"):
            validate_collection_name(name)

    def test_leading_dot_rejected(self):
        """Names starting with a dot are rejected (hidden files)."""
        with pytest.raises(CollectionNameError, match="Invalid collection name"):
            validate_collection_name(".hidden")

    def test_leading_hyphen_rejected(self):
        """Names starting with a hyphen are rejected."""
        with pytest.raises(CollectionNameError, match="Invalid collection name"):
            validate_collection_name("-bad")


# ── API-level integration tests ────────────────────────────────────────


class TestApiLevelValidation:
    """Collection name validation at the REST API level."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        reset_container()
        runtime_root = tmp_path / "runtime"
        settings_path = tmp_path / "settings.yaml"
        settings_payload = {
            "app": {"name": "rag-mcp-validation-test", "environment": "test"},
            "embedding": {"provider": "hash", "dimensions": 64},
            "vector_store": {
                "provider": "chroma",
                "collection_name": "test_default",
                "persist_path": str(runtime_root / "vector_store" / "chroma_live"),
            },
            "ingestion": {
                "chunk_size": 500,
                "chunk_overlap": 50,
                "supported_extensions": [".txt", ".md"],
            },
            "retrieval": {
                "top_k": 5, "dense_top_k": 5, "sparse_top_k": 5,
                "hybrid_top_k": 5, "rrf_k": 60,
                "rerank_enabled": True, "rerank_top_k": 5,
            },
            "rerank": {"provider": "lexical", "enabled": True},
            "observability": {
                "trace_enabled": True,
                "trace_path": str(runtime_root / "traces" / "traces.jsonl"),
            },
            "evaluation": {
                "enabled": True,
                "report_path": str(runtime_root / "evaluations" / "reports.jsonl"),
                "default_test_set_path": "data/evaluations/golden_test_set.json",
                "metrics": ["hit_rate", "mrr"],
                "top_k": 5,
                "persist_reports": True,
            },
            "prompts": {
                "answer_system_prompt_path": "config/prompts/answer_system.txt",
                "answer_user_prompt_path": "config/prompts/answer_user.txt",
            },
            "mcp": {"server_name": "test", "server_version": "0.1.0"},
            "api": {"host": "127.0.0.1", "port": 8000},
        }
        settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
        monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
        runtime_root.mkdir(parents=True, exist_ok=True)
        yield
        reset_container()

    def _client(self) -> TestClient:
        return TestClient(create_app())

    # ── path traversal attacks via query param ─────────────────────

    def test_stats_rejects_path_traversal(self):
        """GET /stats with collection_name=../../etc rejects with 400."""
        client = self._client()
        response = client.get("/api/v1/stats?collection_name=../../etc")
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == 400
        assert "collection name" in body["message"].lower() or "Invalid" in body["message"]

    def test_documents_rejects_path_traversal(self):
        """GET /documents with collection_name=..\\Windows rejects with 400."""
        client = self._client()
        response = client.get("/api/v1/documents?collection_name=..\\Windows")
        assert response.status_code == 400

    def test_stats_empty_collection_name_uses_default(self):
        """GET /stats with collection_name=& (empty) falls back to default (200)."""
        client = self._client()
        response = client.get("/api/v1/stats?collection_name=")
        # Empty string is falsy in Python → get_scope() uses the default
        assert response.status_code == 200

    def test_stats_rejects_reserved_name(self):
        """GET /stats with collection_name=CON rejects with 400."""
        client = self._client()
        response = client.get("/api/v1/stats?collection_name=CON")
        assert response.status_code == 400
        body = response.json()
        assert "reserved" in body["message"].lower()

    def test_stats_rejects_invalid_characters(self):
        """GET /stats with collection_name containing spaces rejects with 400."""
        client = self._client()
        response = client.get("/api/v1/stats?collection_name=foo bar")
        assert response.status_code == 400

    # ── valid names pass ────────────────────────────────────────────

    def test_stats_accepts_valid_collection_name(self):
        """GET /stats with a valid collection name returns 200."""
        client = self._client()
        response = client.get("/api/v1/stats?collection_name=my_project_v2")
        assert response.status_code == 200

    def test_default_health_endpoint_unaffected(self):
        """GET /health (no collection param) still works."""
        client = self._client()
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    # ── request body endpoints ──────────────────────────────────────

    def test_ingest_rejects_path_traversal_in_body(self):
        """POST /ingest with collection_name=../../etc rejects with 400."""
        client = self._client()
        from pathlib import Path
        sample = Path(__file__).resolve().parents[2] / "data" / "documents" / "sample.md"
        response = client.post(
            "/api/v1/ingest",
            json={
                "path": str(sample),
                "collection_name": "../../etc",
            },
        )
        assert response.status_code == 400

    # ── default name validity ───────────────────────────────────────

    def test_default_collection_name_is_valid(self):
        """The default collection name 'test_default' passes validation."""
        # This is implicitly tested by the health check passing above,
        # but we also test it explicitly.
        assert validate_collection_name("test_default") == "test_default"
