"""Local stub LLM provider for development and tests."""

from __future__ import annotations


class StubLlmProvider:
    """Generate deterministic answers from provided retrieval context."""

    model = "stub"

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        metadata: dict | None = None,
    ) -> str:
        """Return a simple answer based on supplied context metadata."""
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
