"""Generation skill: LLM-grounded answer generation with citations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rag_mcp.application.dto.models import GenerateAnswerResponse
from rag_mcp.core.skill_registry import SkillDescriptor, ToolDescriptor

if TYPE_CHECKING:
    from rag_mcp.core.container import ApplicationContainer
    from rag_mcp.core.settings import Settings


class GenerationSkill:
    """Handles grounded answer generation with citations."""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        return SkillDescriptor(
            name="generation",
            version="1.0.0",
            description="LLM-grounded answer generation with citation",
            enabled_by_default=True,
            dependencies=["retrieval"],
        )

    @classmethod
    def register_tools(cls, container: ApplicationContainer) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="generate_answer",
                description="Generate a grounded answer with citations from retrieved knowledge sources.",
                handler=cls._generate_answer(container),
                return_type=GenerateAnswerResponse,
            ),
        ]

    @classmethod
    def wire_container(cls, container: ApplicationContainer, settings: Settings) -> None:
        from rag_mcp.application.use_cases.generate_answer import GenerateAnswerUseCase
        from rag_mcp.infrastructure.prompts.answer_prompt_builder import AnswerPromptBuilder
        from rag_mcp.infrastructure.prompts.template_loader import FilePromptTemplateLoader

        container.prompt_template_loader = FilePromptTemplateLoader()
        container.answer_prompt_builder = AnswerPromptBuilder(
            template_loader=container.prompt_template_loader,
            system_prompt_path=settings.prompts.answer_system_prompt_path,
            user_prompt_path=settings.prompts.answer_user_prompt_path,
        )
        container.generate_answer_use_case = GenerateAnswerUseCase(
            query_use_case=container.query_use_case,
            llm_provider=container.llm_provider,
            trace_collector=container.trace_collector,
            answer_prompt_builder=container.answer_prompt_builder,
        )

    @staticmethod
    def _generate_answer(container: ApplicationContainer):
        from rag_mcp.application.dto.models import GenerateAnswerRequest

        def generate_answer(query: str, top_k: int = 5):
            return container.generate_answer_use_case.execute(
                GenerateAnswerRequest(query=query, top_k=top_k)
            )

        return generate_answer
