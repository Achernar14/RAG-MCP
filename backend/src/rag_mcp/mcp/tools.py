"""MCP tool registration — minimal, read-only knowledge tools for external LLMs.

The MCP channel only exposes tools that help an external LLM *retrieve*
information.  Management operations (ingest, delete, rebuild, evaluation)
and answer generation belong on the REST channel — they are not registered
here.

See ``local/proposals/精简架构重构方案.md`` for the rationale.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from rag_mcp.application.dto.models import (
    CollectionInfoResponse,
    DocumentListItemResponse,
    QueryRequest,
    QueryResponse,
)
from rag_mcp.factory import RAGSystem


def register_mcp_tools(server: FastMCP, rag: RAGSystem) -> None:
    """Register the minimal MCP tool set on *server*.

    Only **read-only knowledge retrieval and browsing** tools are exposed.
    External LLMs use these to look up information and then generate answers
    themselves — the system does not generate answers on their behalf.
    """

    # ── knowledge_search (core) ──────────────────────────────────────

    def knowledge_search(query: str, top_k: int = 5) -> QueryResponse:
        """Search the knowledge base for the most relevant document chunks.

        Use this tool when you need factual information to answer a user's
        question. It returns ranked text chunks with source references.
        """
        return rag.query_use_case.execute(
            QueryRequest(query=query, top_k=top_k)
        )

    server.add_tool(
        knowledge_search,
        name="knowledge_search",
        description=(
            "Search the knowledge base for the most relevant document chunks. "
            "Returns ranked results with source paths and relevance scores."
        ),
        structured_output=True,
    )

    # ── list_documents (browse) ──────────────────────────────────────

    def list_documents(collection_name: str | None = None) -> list[DocumentListItemResponse]:
        """List all ingested documents in the knowledge base."""
        return rag.list_documents_use_case.execute(collection_name)

    server.add_tool(
        list_documents,
        name="list_documents",
        description="List all documents currently ingested in the knowledge base.",
        structured_output=True,
    )

    # ── list_collections (browse) ────────────────────────────────────

    def list_collections() -> list[CollectionInfoResponse]:
        """List all available collections and their document counts."""
        return rag.list_collections_use_case.execute()

    server.add_tool(
        list_collections,
        name="list_collections",
        description="List all available collections with document and chunk counts.",
        structured_output=True,
    )
