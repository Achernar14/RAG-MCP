"""Grounded answer prompt composition."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass(frozen=True)
class RenderedPrompt:
    """Rendered prompt pair for answer generation."""

    system_prompt: str
    user_prompt: str
    system_prompt_path: str
    user_prompt_path: str
    system_prompt_fingerprint: str
    user_prompt_fingerprint: str
    system_prompt_length: int
    user_prompt_length: int


class AnswerPromptBuilder:
    """Render system and user prompts from configurable templates."""

    def __init__(
        self,
        *,
        template_loader,
        system_prompt_path: str,
        user_prompt_path: str,
    ) -> None:
        self.template_loader = template_loader
        self.system_prompt_path = system_prompt_path
        self.user_prompt_path = user_prompt_path

    def build(self, *, query: str, source_items: list[dict[str, object]]) -> RenderedPrompt:
        """Render the prompt pair for a grounded answer request."""
        system_template = self.template_loader.load(self.system_prompt_path)
        user_template = self.template_loader.load(self.user_prompt_path)
        sources_block = self._render_sources(source_items)
        system_prompt = system_template.format()
        user_prompt = user_template.format(query=query, sources=sources_block)
        return RenderedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            system_prompt_path=self.system_prompt_path,
            user_prompt_path=self.user_prompt_path,
            system_prompt_fingerprint=_fingerprint(system_prompt),
            user_prompt_fingerprint=_fingerprint(user_prompt),
            system_prompt_length=len(system_prompt),
            user_prompt_length=len(user_prompt),
        )

    def _render_sources(self, source_items: list[dict[str, object]]) -> str:
        lines: list[str] = []
        for item in source_items:
            lines.append(
                "[{index}] {source_path} :: {snippet}".format(
                    index=item.get("index", ""),
                    source_path=item.get("source_path", ""),
                    snippet=item.get("snippet", ""),
                )
            )
        return "\n".join(lines).strip()


def _fingerprint(text: str) -> str:
    """Return a short stable fingerprint for prompt observability."""
    return sha256(text.encode("utf-8")).hexdigest()[:16]
