"""Local stub LLM provider for development and tests."""

from __future__ import annotations

from collections.abc import Iterator

from rag_mcp.domain.repositories.contracts import LlmProvider


class StubLlmProvider(LlmProvider):
    """Generate deterministic answers from provided retrieval context."""

    model = "stub"

    # ── shared answer builder ───────────────────────────────────────────

    def _build_answer(
        self,
        prompt: str,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Build the full answer from retrieval context."""
        metadata = metadata or {}
        sources = metadata.get("sources", [])
        query = metadata.get("query", "")
        if not sources:
            return f"No grounded answer could be generated for: {query}"

        snippets: list[str] = []
        for item in sources[:2]:
            snippet = str(item.get("snippet", "")).strip()
            if snippet:
                snippets.append(snippet)

        if not snippets:
            return f"Grounded answer for '{query}' is unavailable because no source snippets were provided."

        joined = " ".join(snippets)
        return f"Grounded answer for '{query}': {joined}"

    # ── synchronous generation ──────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Return a simple answer based on supplied context metadata."""
        return self._build_answer(prompt, system_prompt, metadata)

    # ── streaming generation ────────────────────────────────────────────

    def generate_stream(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> Iterator[str]:
        """Simulate token-by-token streaming for development and tests.

        Splits the stub answer into word-level chunks (preserving
        whitespace between words) so that SSE consumers see incremental
        output similar to a real streaming LLM.
        """
        full = self._build_answer(prompt, system_prompt, metadata)
        # Split on word boundaries while preserving spaces
        words = full.split(" ")
        for i, word in enumerate(words):
            chunk = word if i == 0 else f" {word}"
            yield chunk
