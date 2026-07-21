"""Compatibility re-exports — prefer :mod:`rag_mcp.factory` for new code."""

from rag_mcp.factory import (
    RAGSystem,
    create_rag_system,
    get_rag,
    reset_rag,
)

# Legacy aliases
ApplicationContainer = RAGSystem
get_container = get_rag
reset_container = reset_rag
