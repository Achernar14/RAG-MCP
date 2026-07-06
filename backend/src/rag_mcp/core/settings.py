"""Configuration loading for the RAG MCP project."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from rag_mcp.core.exceptions import ConfigurationError


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = PACKAGE_ROOT.parents[1]
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml"
EXAMPLE_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.yaml.example"
SETTINGS_ENV_VAR = "RAG_MCP_SETTINGS_PATH"
DOTENV_PATH = PROJECT_ROOT / ".env"


def resolve_project_path(path: str | Path) -> Path:
    """Resolve relative paths against the project root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


class AppSettings(BaseModel):
    name: str = "rag-mcp"
    environment: str = "development"


class EmbeddingSettings(BaseModel):
    provider: str = "hash"
    dimensions: int = 64


class EmbeddingProviderOptions(BaseModel):
    api_base: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    timeout_seconds: float = 30.0


class LlmSettings(BaseModel):
    provider: str = "stub"
    enabled: bool = False
    api_base: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    temperature: float = 0.1
    max_tokens: int = 1024
    timeout_seconds: float = 60.0


class VisionLlmSettings(BaseModel):
    provider: str = "disabled"
    enabled: bool = False
    api_base: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    timeout_seconds: float = 60.0


class VectorStoreSettings(BaseModel):
    provider: str = "weaviate"
    persist_path: str = "data/vector_store/chroma"
    collection_name: str = "RAG_MCP"

    # Weaviate mode: "embedded" (Linux/macOS only) or "remote" (cross-platform)
    weaviate_mode: str = "embedded"

    # Weaviate Embedded options (used when weaviate_mode == "embedded")
    weaviate_persistence_data_path: str = "data/vector_store/weaviate"
    weaviate_version: str = "1.37.2"
    weaviate_hostname: str = "127.0.0.1"
    weaviate_port: int = 8079

    # Weaviate Remote options (used when weaviate_mode == "remote")
    weaviate_grpc_port: int = 50051
    weaviate_api_key: str | None = None


class IngestionSettings(BaseModel):
    chunk_size: int = 500
    chunk_overlap: int = 50
    normalize_whitespace: bool = True
    preserve_paragraph_breaks: bool = True
    boundary_scan_chars: int = 80
    min_chunk_length: int = 40
    supported_extensions: list[str] = Field(default_factory=lambda: [".txt", ".md", ".pdf"])
    max_file_size_bytes: int = 20 * 1024 * 1024
    allow_hidden_files: bool = False


class RetrievalSettings(BaseModel):
    top_k: int = 5
    dense_top_k: int = 5
    sparse_top_k: int = 5
    hybrid_top_k: int = 5
    rrf_k: int = 60
    rerank_enabled: bool = True
    rerank_top_k: int = 5


class RerankSettings(BaseModel):
    provider: str = "lexical"
    enabled: bool = True
    model: str | None = None
    api_base: str | None = None
    api_key_env: str | None = None
    score_threshold: float | None = None
    timeout_seconds: float = 30.0


class ObservabilitySettings(BaseModel):
    trace_enabled: bool = True
    trace_path: str = "data/traces/traces.jsonl"


class EvaluationSettings(BaseModel):
    enabled: bool = True
    report_path: str = "data/evaluations/reports.jsonl"
    default_test_set_path: str = "data/evaluations/golden_test_set.json"
    metrics: list[str] = Field(default_factory=lambda: ["hit_rate", "mrr"])
    top_k: int = 5
    persist_reports: bool = True


class PromptSettings(BaseModel):
    answer_system_prompt_path: str = "config/prompts/answer_system.txt"
    answer_user_prompt_path: str = "config/prompts/answer_user.txt"


class McpSettings(BaseModel):
    server_name: str = "rag-mcp"
    server_version: str = "0.1.0"
    transport: str = "stdio"  # "stdio" | "streamable-http" | "sse"
    host: str = "127.0.0.1"
    port: int = 9000
    mount_path: str = "/mcp"  # URL path for HTTP transports


class ApiSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000


class RedisCacheSettings(BaseModel):
    embedding_enabled: bool = False
    retrieval_enabled: bool = False


class RedisSettings(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    password_env: str | None = None
    max_connections: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    ttl_embedding: int = 604800  # 7 days
    ttl_retrieval: int = 3600  # 1 hour
    cache: RedisCacheSettings = Field(default_factory=RedisCacheSettings)


class ApiKeyAuthSettings(BaseModel):
    """API Key authentication settings for REST endpoints."""
    enabled: bool = False
    api_key_env: str | None = "RAG_MCP_API_KEY"
    api_key_direct: str | None = None  # Direct key value (takes precedence over env var)
    header_name: str = "X-API-Key"


class SkillSettings(BaseModel):
    """Per-skill enablement flags."""

    ingestion: bool = True
    retrieval: bool = True
    generation: bool = True
    document_management: bool = True
    evaluation: bool = True
    observability: bool = True


class Settings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    embedding_provider: EmbeddingProviderOptions = Field(default_factory=EmbeddingProviderOptions)
    llm: LlmSettings = Field(default_factory=LlmSettings)
    vision_llm: VisionLlmSettings = Field(default_factory=VisionLlmSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    evaluation: EvaluationSettings = Field(default_factory=EvaluationSettings)
    prompts: PromptSettings = Field(default_factory=PromptSettings)
    mcp: McpSettings = Field(default_factory=McpSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    api_key: ApiKeyAuthSettings = Field(default_factory=ApiKeyAuthSettings)
    skills: SkillSettings = Field(default_factory=SkillSettings)


def ensure_default_config() -> Path:
    """Ensure a usable settings file exists."""
    if DEFAULT_SETTINGS_PATH.exists():
        return DEFAULT_SETTINGS_PATH
    if not EXAMPLE_SETTINGS_PATH.exists():
        raise ConfigurationError(
            f"Missing configuration template: {EXAMPLE_SETTINGS_PATH}"
        )
    DEFAULT_SETTINGS_PATH.write_text(
        EXAMPLE_SETTINGS_PATH.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return DEFAULT_SETTINGS_PATH


def load_settings(path: str | Path | None = None) -> Settings:
    """Load application settings from YAML."""
    load_dotenv(DOTENV_PATH)
    configured_path = path or os.getenv(SETTINGS_ENV_VAR)
    settings_path = (
        resolve_project_path(configured_path) if configured_path else ensure_default_config()
    )
    if not settings_path.exists():
        raise ConfigurationError(f"Settings file not found: {settings_path}")

    raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ConfigurationError("Settings root must be a mapping")

    try:
        return Settings.model_validate(raw)
    except Exception as exc:  # pragma: no cover - pydantic provides detail
        raise ConfigurationError(str(exc)) from exc


def settings_to_dict(settings: Settings) -> dict[str, Any]:
    """Convert settings to a plain dictionary."""
    return settings.model_dump()
