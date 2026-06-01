"""Skill registry for modular capability management."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from rag_mcp.core.container import ApplicationContainer
    from rag_mcp.core.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class ToolDescriptor:
    """Metadata for a single MCP tool function."""

    name: str
    description: str
    handler: Callable[..., Any]
    return_type: type | None = None


@dataclass
class SkillDescriptor:
    """Declarative metadata for a skill module."""

    name: str
    version: str
    description: str
    enabled_by_default: bool = True
    tools: list[ToolDescriptor] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


class SkillModule(Protocol):
    """Protocol that each skill module must implement."""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        """Return declarative metadata for this skill."""
        ...

    @classmethod
    def register_tools(cls, container: ApplicationContainer) -> list[ToolDescriptor]:
        """Wire use cases from the container and return tool descriptors."""
        ...

    @classmethod
    def wire_container(cls, container: ApplicationContainer, settings: Settings) -> None:
        """Set up skill-specific dependencies on the container."""
        ...


class SkillRegistry:
    """Central registry for discovering and enabling skill modules."""

    def __init__(self) -> None:
        self._modules: dict[str, type[SkillModule]] = {}
        self._descriptors: dict[str, SkillDescriptor] = {}
        self._enabled: set[str] = set()

    def register(self, module_cls: type[SkillModule]) -> None:
        """Register a skill module class."""
        desc = module_cls.descriptor()
        self._modules[desc.name] = module_cls
        self._descriptors[desc.name] = desc

    def enable(self, skill_name: str) -> None:
        """Enable a registered skill."""
        if skill_name not in self._modules:
            raise ValueError(f"Unknown skill: {skill_name}")
        self._enabled.add(skill_name)

    def disable(self, skill_name: str) -> None:
        """Disable a registered skill."""
        self._enabled.discard(skill_name)

    def is_enabled(self, skill_name: str) -> bool:
        """Check whether a skill is enabled."""
        return skill_name in self._enabled

    def get_enabled_tools(self, container: ApplicationContainer) -> list[ToolDescriptor]:
        """Collect tools from all enabled skills, respecting dependency order."""
        tools: list[ToolDescriptor] = []
        for skill_name in self._topological_order():
            if skill_name in self._enabled:
                module = self._modules[skill_name]
                tools.extend(module.register_tools(container))
        return tools

    def wire_all(self, container: ApplicationContainer, settings: Settings) -> None:
        """Wire container dependencies for all enabled skills."""
        for skill_name in self._topological_order():
            if skill_name in self._enabled:
                module = self._modules[skill_name]
                module.wire_container(container, settings)

    def _topological_order(self) -> list[str]:
        """Sort skills by dependency order (Kahn's algorithm)."""
        in_degree: dict[str, int] = {name: 0 for name in self._modules}
        for name, desc in self._descriptors.items():
            for dep in desc.dependencies:
                if dep in in_degree:
                    in_degree[name] += 1
        queue = [name for name, deg in in_degree.items() if deg == 0]
        ordered: list[str] = []
        while queue:
            name = queue.pop(0)
            ordered.append(name)
            for other_name, desc in self._descriptors.items():
                if name in desc.dependencies:
                    in_degree[other_name] -= 1
                    if in_degree[other_name] == 0:
                        queue.append(other_name)
        return ordered

    @property
    def all_skills(self) -> dict[str, SkillDescriptor]:
        """Return descriptors for all registered skills."""
        return dict(self._descriptors)

    @property
    def enabled_skills(self) -> set[str]:
        """Return names of all enabled skills."""
        return set(self._enabled)
