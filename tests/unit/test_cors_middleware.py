"""Unit tests for CORS middleware configuration and behaviour."""

import pytest
import yaml
from fastapi.testclient import TestClient

from rag_mcp.core.container import reset_container
from rag_mcp.core.settings import CorsSettings, Settings
from rag_mcp.main import create_app


class TestCorsSettingsDefaults:
    """Verify pydantic model defaults are development-friendly."""

    def test_defaults_are_permissive_for_local_dev(self):
        cors = CorsSettings()
        assert cors.enabled is True
        assert cors.allow_origins == ["*"]
        assert cors.allow_credentials is True

    def test_disabled_via_constructor(self):
        cors = CorsSettings(enabled=False)
        assert cors.enabled is False

    def test_restrict_origins(self):
        cors = CorsSettings(allow_origins=["https://example.com"])
        assert cors.allow_origins == ["https://example.com"]

    def test_settings_model_populates_cors_default(self):
        settings = Settings()
        assert settings.cors.enabled is True
        assert settings.cors.allow_origins == ["*"]


class TestCorsHeadersInResponse:
    """Verify CORS headers are present in API responses when enabled."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        reset_container()
        runtime_root = tmp_path / "runtime"
        settings_path = tmp_path / "settings.yaml"
        settings_payload = {
            "app": {"name": "rag-mcp-cors-test", "environment": "test"},
            "embedding": {"provider": "hash", "dimensions": 64},
            "vector_store": {
                "provider": "chroma",
                "collection_name": "cors_test",
                "persist_path": str(runtime_root / "vector_store" / "chroma_live"),
            },
            "ingestion": {
                "chunk_size": 500,
                "chunk_overlap": 50,
                "supported_extensions": [".txt", ".md", ".html"],
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
            "mcp": {"server_name": "rag-mcp-cors", "server_version": "0.1.0"},
            "api": {"host": "127.0.0.1", "port": 8000},
            "cors": {
                "enabled": True,
                "allow_origins": ["http://localhost:8501"],
                "allow_methods": ["GET", "POST", "DELETE", "OPTIONS"],
                "allow_headers": ["*"],
                "allow_credentials": True,
            },
        }
        settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
        monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
        runtime_root.mkdir(parents=True, exist_ok=True)
        self._runtime_root = runtime_root
        yield
        reset_container()

    @property
    def _client(self) -> TestClient:
        app = create_app()
        return TestClient(app)

    # ── origin → CORS header mapping ──────────────────────────────────

    def test_allowed_origin_receives_cors_headers(self):
        """Requests from an allowed origin get Access-Control-Allow-Origin."""
        client = self._client
        response = client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:8501"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8501"
        # credentials enabled → must echo specific origin, not wildcard
        assert "Access-Control-Allow-Credentials" in response.headers
        assert response.headers["Access-Control-Allow-Credentials"] == "true"

    def test_disallowed_origin_does_not_receive_cors_headers(self):
        """Requests from a non-whitelisted origin get no CORS headers."""
        client = self._client
        response = client.get(
            "/api/v1/health",
            headers={"Origin": "https://evil.example.com"},
        )
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_no_origin_header_no_cors_headers(self):
        """Same-origin requests (no Origin header) don't need CORS headers."""
        client = self._client
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        # With specific origins (not wildcard), no Origin → no ACAO header
        assert "Access-Control-Allow-Origin" not in response.headers

    def test_wildcard_origin_returns_wildcard(self, tmp_path, monkeypatch):
        """When allow_origins=['*'] and credentials disabled, ACAO should be '*'."""
        reset_container()
        settings_path = tmp_path / "wildcard_settings.yaml"
        settings_payload = {
            "app": {"name": "test", "environment": "test"},
            "embedding": {"provider": "hash", "dimensions": 64},
            "vector_store": {
                "provider": "chroma",
                "collection_name": "test",
                "persist_path": str(tmp_path / "vs"),
            },
            "ingestion": {"supported_extensions": [".txt"]},
            "retrieval": {
                "top_k": 5, "dense_top_k": 5, "sparse_top_k": 5,
                "hybrid_top_k": 5, "rrf_k": 60,
                "rerank_enabled": True, "rerank_top_k": 5,
            },
            "rerank": {"provider": "lexical", "enabled": True},
            "observability": {"trace_enabled": True, "trace_path": str(tmp_path / "t.jsonl")},
            "evaluation": {
                "enabled": True,
                "report_path": str(tmp_path / "r.jsonl"),
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
            # allow_credentials=false so wildcard '*' is permitted
            "cors": {"enabled": True, "allow_origins": ["*"], "allow_credentials": False},
        }
        settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
        monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))

        app = create_app()
        client = TestClient(app)
        response = client.get(
            "/api/v1/health",
            headers={"Origin": "http://any-random-origin.example.com"},
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "*"
        reset_container()

    def test_options_preflight_returns_cors_headers(self):
        """OPTIONS preflight should return appropriate CORS headers."""
        client = self._client
        response = client.options(
            "/api/v1/query",
            headers={
                "Origin": "http://localhost:8501",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8501"


class TestCorsDisabled:
    """When CORS is disabled, no CORS headers should be injected."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        reset_container()
        settings_path = tmp_path / "no_cors_settings.yaml"
        settings_payload = {
            "app": {"name": "test", "environment": "test"},
            "embedding": {"provider": "hash", "dimensions": 64},
            "vector_store": {
                "provider": "chroma",
                "collection_name": "test",
                "persist_path": str(tmp_path / "vs"),
            },
            "ingestion": {"supported_extensions": [".txt"]},
            "retrieval": {
                "top_k": 5, "dense_top_k": 5, "sparse_top_k": 5,
                "hybrid_top_k": 5, "rrf_k": 60,
                "rerank_enabled": True, "rerank_top_k": 5,
            },
            "rerank": {"provider": "lexical", "enabled": True},
            "observability": {"trace_enabled": True, "trace_path": str(tmp_path / "t.jsonl")},
            "evaluation": {
                "enabled": True,
                "report_path": str(tmp_path / "r.jsonl"),
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
            "cors": {"enabled": False},
        }
        settings_path.write_text(yaml.safe_dump(settings_payload), encoding="utf-8")
        monkeypatch.setenv("RAG_MCP_SETTINGS_PATH", str(settings_path))
        yield
        reset_container()

    def test_cors_disabled_no_headers(self):
        """With cors.enabled=false, no Access-Control-* headers should appear."""
        app = create_app()
        client = TestClient(app)
        response = client.get(
            "/api/v1/health",
            headers={"Origin": "http://localhost:8501"},
        )
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response.headers
