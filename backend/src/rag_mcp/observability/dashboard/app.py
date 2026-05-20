"""Streamlit dashboard entrypoint."""

from __future__ import annotations

import streamlit as st

from rag_mcp.observability.dashboard.pages import render_documents_page
from rag_mcp.observability.dashboard.pages import render_evaluations_page
from rag_mcp.observability.dashboard.pages import render_ingestion_page
from rag_mcp.observability.dashboard.pages import render_overview_page
from rag_mcp.observability.dashboard.pages import render_answers_page
from rag_mcp.observability.dashboard.pages import render_traces_page


def main() -> None:
    """Run the dashboard application."""
    st.set_page_config(
        page_title="RAG MCP Dashboard",
        page_icon="R",
        layout="wide",
    )

    pages = {
        "Overview": render_overview_page,
        "Ingestion Manager": render_ingestion_page,
        "Answers": render_answers_page,
        "Documents": render_documents_page,
        "Traces": render_traces_page,
        "Evaluations": render_evaluations_page,
    }
    if st.session_state.get("dashboard_selected_page") not in pages:
        st.session_state["dashboard_selected_page"] = "Overview"
    selected = st.sidebar.radio(
        "Page",
        list(pages.keys()),
        key="dashboard_selected_page",
    )
    pages[selected]()


if __name__ == "__main__":
    main()
