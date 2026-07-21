"""MCP tool registration — minimal, read-only knowledge tools for external LLMs.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from rag_mcp.application.handlers import (
    list_collections,
    list_documents,
    search_knowledge,
)
from rag_mcp.factory import RAGSystem


def register_mcp_tools(server: FastMCP, rag: RAGSystem) -> None:
    """Register the minimal MCP tool set on *server* — only read-only
    knowledge retrieval and browsing tools."""

    # ── knowledge_search (core) ──────────────────────────────────────

    def _knowledge_search(query: str, top_k: int = 5) -> dict:
        """Search the knowledge base for relevant document chunks."""
        return search_knowledge(rag, query, top_k)

    server.add_tool(
        _knowledge_search,
        name="knowledge_search",
        description=(
            "Search the knowledge base for the most relevant document chunks. "
            "Returns ranked results with source paths and relevance scores."
        ),
        structured_output=False,
    )

    # ── list_documents (browse) ──────────────────────────────────────

    def _list_documents(collection_name: str | None = None) -> list[dict]:
        """List all ingested documents in the knowledge base."""
        return list_documents(rag, collection_name)

    server.add_tool(
        _list_documents,
        name="list_documents",
        description="List all documents currently ingested in the knowledge base.",
        structured_output=False,
    )

    # ── list_collections (browse) ────────────────────────────────────

    def _list_collections() -> list[dict]:
        """List all available collections and their document counts."""
        return list_collections(rag)

    server.add_tool(
        _list_collections,
        name="list_collections",
        description="List all available collections with document and chunk counts.",
        structured_output=False,
    )
