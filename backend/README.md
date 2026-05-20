# RAG-MCP Backend

Backend package for the modular RAG-MCP project.

## Install

This project uses `pyproject.toml` as the single dependency source.

Core install:

```bash
pip install -e ./backend
```

Development install:

```bash
pip install -e ./backend[dev]
```

## Run MCP Server

Start the official SDK-backed MCP stdio server:

```bash
PYTHONPATH=backend/src python -m rag_mcp.mcp.server
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH='backend/src'
python -m rag_mcp.mcp.server
```
