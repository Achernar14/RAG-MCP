"""Provider factory helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from rag_mcp.core.exceptions import ConfigurationError
from rag_mcp.core.settings import Settings
from rag_mcp.domain.services.reranking import BaseReranker
from rag_mcp.infrastructure.embedding.hash_embedding import HashEmbeddingProvider
from rag_mcp.infrastructure.embedding.zhipu_embedding import ZhipuEmbeddingProvider
from rag_mcp.infrastructure.llm.openai_compatible_llm import OpenAICompatibleLlmProvider
from rag_mcp.infrastructure.llm.stub_llm import StubLlmProvider
from rag_mcp.infrastructure.rerank.cross_encoder_reranker import CrossEncoderReranker


EmbeddingFactory = Callable[[Settings], object]
LlmFactory = Callable[[Settings], object]
RerankerFactory = Callable[[Settings], BaseReranker | None]
VisionFactory = Callable[[Settings], object | None]


def create_embedding_provider(settings: Settings):
    """Create an embedding provider from configuration."""
    provider = settings.embedding.provider.lower()
    return _create_from_registry(
        provider_type="embedding",
        provider_name=provider,
        settings=settings,
        factories={
            "hash": _create_hash_embedding_provider,
            "zhipu": _create_zhipu_embedding_provider,
        },
    )


def create_llm_provider(settings: Settings):
    """Create an LLM provider from configuration."""
    provider = settings.llm.provider.lower()
    if provider == "stub" or not settings.llm.enabled:
        return _create_stub_llm_provider(settings)
    return _create_from_registry(
        provider_type="llm",
        provider_name=provider,
        settings=settings,
        factories={
            "deepseek": _create_openai_compatible_llm_provider,
        },
    )


def create_reranker(settings: Settings) -> BaseReranker | None:
    """Create a Cross-Encoder reranker from configuration."""
    if not settings.retrieval.rerank_enabled or not settings.rerank.enabled:
        return None

    return CrossEncoderReranker(model_name=settings.rerank.model)


def create_vision_llm_provider(settings: Settings) -> object | None:
    """Create a vision provider boundary from configuration."""
    if not settings.vision_llm.enabled:
        return None

    provider = settings.vision_llm.provider.lower()
    if provider in {"disabled", "none"}:
        return None

    return _create_from_registry(
        provider_type="vision llm",
        provider_name=provider,
        settings=settings,
        factories={},
    )


def _create_hash_embedding_provider(settings: Settings) -> HashEmbeddingProvider:
    return HashEmbeddingProvider(dimensions=settings.embedding.dimensions)


def _create_zhipu_embedding_provider(settings: Settings) -> ZhipuEmbeddingProvider:
    return ZhipuEmbeddingProvider(
        api_base=settings.embedding_provider.api_base,
        api_key_env=settings.embedding_provider.api_key_env,
        model=settings.embedding_provider.model,
        timeout_seconds=settings.embedding_provider.timeout_seconds,
    )


def _create_stub_llm_provider(settings: Settings) -> StubLlmProvider:
    del settings
    return StubLlmProvider()


def _create_openai_compatible_llm_provider(settings: Settings) -> OpenAICompatibleLlmProvider:
    return OpenAICompatibleLlmProvider(
        api_base=settings.llm.api_base,
        api_key_env=settings.llm.api_key_env,
        model=settings.llm.model,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
        timeout_seconds=settings.llm.timeout_seconds,
    )


def _create_from_registry(
    *,
    provider_type: str,
    provider_name: str,
    settings: Settings,
    factories: dict[str, Callable[[Settings], Any]],
) -> Any:
    """Resolve a provider factory from a simple registry."""
    try:
        return factories[provider_name](settings)
    except KeyError as exc:
        raise ConfigurationError(f"Unsupported {provider_type} provider: {provider_name}") from exc
