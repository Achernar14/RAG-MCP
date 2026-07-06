"""Grounded answer generation use case."""

from __future__ import annotations

import time
from collections.abc import Iterator

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

    # ── shared helpers ──────────────────────────────────────────────────

    def _prepare(
        self, request: GenerateAnswerRequest
    ) -> tuple:
        """Run retrieval and build the prompt; return shared context."""
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

        return (
            query_response,
            source_payload,
            rendered_prompt,
            trace,
            llm_provider_name,
            llm_model,
        )

    def _finish_trace(
        self,
        trace: TraceContext,
        generated_by_llm: bool,
        llm_provider_name: str,
        llm_model: str | None,
        source_count: int,
        generation_started: float,
        error: str | None = None,
    ) -> None:
        """Record the llm_generate stage, finish and collect the trace."""
        trace.record_stage(
            "llm_generate",
            {
                "provider": llm_provider_name,
                "model": llm_model,
                "fallback": error is not None,
                "source_count": source_count,
                **({"error": error} if error else {}),
            },
            (time.monotonic() - generation_started) * 1000.0,
        )
        trace.finish()
        self.trace_collector.collect(trace)

    # ── synchronous generation ──────────────────────────────────────────

    def execute(self, request: GenerateAnswerRequest) -> GenerateAnswerResponse:
        """Run retrieval first, then generate a grounded answer."""
        (
            query_response,
            source_payload,
            rendered_prompt,
            trace,
            llm_provider_name,
            llm_model,
        ) = self._prepare(request)

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
        except ProviderError as exc:
            generation_error = str(exc)
            answer = self._build_fallback_answer(query_response)

        self._finish_trace(
            trace,
            generated_by_llm,
            llm_provider_name,
            llm_model,
            len(source_payload),
            generation_started,
            error=generation_error,
        )

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

    # ── streaming generation ────────────────────────────────────────────

    def execute_stream(
        self, request: GenerateAnswerRequest
    ) -> Iterator[dict]:
        """Stream retrieval results + LLM tokens as SSE-event dicts.

        Yields ``{"event": "<type>", "data": {...}}`` dicts in order:

        1. ``meta`` — trace metadata (trace_id, rerank_applied)
        2. ``sources`` — retrieved source items
        3. ``token`` — one or more text delta chunks
        4. ``done`` — completion with generation stats

        On provider error, yields a fallback answer as token(s) followed
        by an ``error`` event instead of ``done``.
        """
        (
            query_response,
            source_payload,
            rendered_prompt,
            trace,
            llm_provider_name,
            llm_model,
        ) = self._prepare(request)

        # ── event 1: metadata ───────────────────────────────────────
        yield {
            "event": "meta",
            "data": {
                "trace_id": trace.trace_id,
                "rerank_applied": query_response.rerank_applied,
            },
        }

        # ── event 2: sources ─────────────────────────────────────────
        yield {
            "event": "sources",
            "data": {
                "sources": [
                    item.model_dump() for item in query_response.sources
                ],
            },
        }

        # ── event 3+: tokens (or fallback) ───────────────────────────
        generated_by_llm = False
        generation_error: str | None = None
        generation_started = time.monotonic()

        try:
            for token in self.llm_provider.generate_stream(
                rendered_prompt.user_prompt,
                system_prompt=rendered_prompt.system_prompt,
                metadata={
                    "query": request.query,
                    "sources": source_payload,
                },
            ):
                generated_by_llm = True
                yield {"event": "token", "data": {"delta": token}}

            # ── event N: done ────────────────────────────────────
            self._finish_trace(
                trace,
                True,
                llm_provider_name,
                llm_model,
                len(source_payload),
                generation_started,
            )
            yield {
                "event": "done",
                "data": {
                    "trace_id": trace.trace_id,
                    "generated_by_llm": True,
                },
            }

        except ProviderError as exc:
            generation_error = str(exc)
            # Yield fallback answer as a single token chunk
            fallback = self._build_fallback_answer(query_response)
            if fallback:
                yield {"event": "token", "data": {"delta": fallback}}

            self._finish_trace(
                trace,
                False,
                llm_provider_name,
                llm_model,
                len(source_payload),
                generation_started,
                error=generation_error,
            )
            yield {
                "event": "error",
                "data": {
                    "trace_id": trace.trace_id,
                    "generated_by_llm": False,
                    "error": generation_error,
                },
            }

    def _build_fallback_answer(self, query_response) -> str:
        if not query_response.sources:
            return f"未能基于检索结果生成回答：{query_response.query}"

        snippets = [item.snippet.strip() for item in query_response.sources[:2] if item.snippet.strip()]
        if not snippets:
            return f"未能基于检索结果生成回答：{query_response.query}"

        return "基于检索结果的降级回答：\n" + "\n".join(
            f"{index}. {snippet}" for index, snippet in enumerate(snippets, start=1)
        )
