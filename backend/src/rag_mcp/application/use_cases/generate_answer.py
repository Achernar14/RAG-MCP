"""Grounded answer generation use case."""

from __future__ import annotations

import time

from rag_mcp.application.dto.models import (
    GenerateAnswerRequest,
    GenerateAnswerResponse,
    QueryRequest,
)
from rag_mcp.core.exceptions import ProviderError
from rag_mcp.core.tracing import TraceContext


class GenerateAnswerUseCase:
    """Generate a grounded answer on top of retrieval results."""

    def __init__(
        self,
        query_use_case,
        llm_provider,
        trace_collector,
        answer_prompt_builder,
    ) -> None:
        self.query_use_case = query_use_case
        self.llm_provider = llm_provider
        self.trace_collector = trace_collector
        self.answer_prompt_builder = answer_prompt_builder

    def execute(self, request: GenerateAnswerRequest) -> GenerateAnswerResponse:
        """Run retrieval first, then generate a grounded answer."""
        query_response = self.query_use_case.execute(
            QueryRequest(
                query=request.query,
                top_k=request.top_k,
                collection_name=request.collection_name,
            )
        )
        llm_provider_name = self.llm_provider.__class__.__name__
        llm_model = getattr(self.llm_provider, "model", None)

        trace = TraceContext(
            trace_type="answer_generation",
            metadata={
                "query": request.query,
                "top_k": request.top_k,
                "query_trace_id": query_response.trace_id,
                "rerank_applied": query_response.rerank_applied,
                "llm_provider": llm_provider_name,
                "llm_model": llm_model,
                "prompt_system_path": self.answer_prompt_builder.system_prompt_path,
                "prompt_user_path": self.answer_prompt_builder.user_prompt_path,
            },
        )

        source_payload = [item.model_dump() for item in query_response.sources]
        prompt_started = time.monotonic()
        rendered_prompt = self.answer_prompt_builder.build(
            query=request.query,
            source_items=source_payload,
        )
        trace.record_stage(
            "prompt_build",
            {
                "source_count": len(query_response.sources),
                "query_trace_id": query_response.trace_id,
                "system_prompt_path": rendered_prompt.system_prompt_path,
                "user_prompt_path": rendered_prompt.user_prompt_path,
                "system_prompt_fingerprint": rendered_prompt.system_prompt_fingerprint,
                "user_prompt_fingerprint": rendered_prompt.user_prompt_fingerprint,
                "system_prompt_length": rendered_prompt.system_prompt_length,
                "user_prompt_length": rendered_prompt.user_prompt_length,
            },
            (time.monotonic() - prompt_started) * 1000.0,
        )

        answer = ""
        generated_by_llm = False
        generation_error: str | None = None
        generation_started = time.monotonic()
        try:
            answer = self.llm_provider.generate(
                rendered_prompt.user_prompt,
                system_prompt=rendered_prompt.system_prompt,
                metadata={
                    "query": request.query,
                    "sources": source_payload,
                },
            )
            generated_by_llm = True
            trace.record_stage(
                "llm_generate",
                {
                    "provider": llm_provider_name,
                    "model": llm_model,
                    "fallback": False,
                    "source_count": len(source_payload),
                },
                (time.monotonic() - generation_started) * 1000.0,
            )
        except ProviderError as exc:
            generation_error = str(exc)
            answer = self._build_fallback_answer(query_response)
            trace.record_stage(
                "llm_generate",
                {
                    "provider": llm_provider_name,
                    "model": llm_model,
                    "fallback": True,
                    "source_count": len(source_payload),
                    "error": generation_error,
                },
                (time.monotonic() - generation_started) * 1000.0,
            )
        trace.finish()
        self.trace_collector.collect(trace)

        return GenerateAnswerResponse(
            query=request.query,
            answer=answer,
            results=query_response.results,
            sources=query_response.sources,
            trace_id=trace.trace_id,
            rerank_applied=query_response.rerank_applied,
            generated_by_llm=generated_by_llm,
            generation_error=generation_error,
        )

    def _build_fallback_answer(self, query_response) -> str:
        if not query_response.sources:
            return f"未能基于检索结果生成回答：{query_response.query}"

        snippets = [item.snippet.strip() for item in query_response.sources[:2] if item.snippet.strip()]
        if not snippets:
            return f"未能基于检索结果生成回答：{query_response.query}"

        return "基于检索结果的降级回答：\n" + "\n".join(
            f"{index}. {snippet}" for index, snippet in enumerate(snippets, start=1)
        )
