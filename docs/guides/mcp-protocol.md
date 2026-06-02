# MCP 协议层详解 — 从传输到工具执行

## 1. 什么是 MCP

MCP（Model Context Protocol，模型上下文协议）是 Anthropic 提出的开放协议，让 LLM 应用能够通过统一标准与外部工具和数据源交互。

通俗理解：**MCP 就是 LLM 世界的 USB 接口。** 无论你的 LLM 客户端是 Claude Desktop、Cursor 还是自研应用，只要支持 MCP，就能即插即用地调用 RAG-MCP 提供的所有能力。

```
┌────────────────────────────────────────────────────────────────┐
│                MCP 在项目中的角色                                │
│                                                                │
│   用户 ←→ LLM Client ←─ MCP 协议 ─→ RAG-MCP Server           │
│            (Claude        (stdio)        (15 个工具)           │
│             Desktop,                                            │
│             Cursor,         │                                   │
│             ...)            │ 标准化的 JSON-RPC 通信            │
│                              │                                   │
│                   ┌──────────┴──────────┐                      │
│                   │  三种 MCP 原语       │                      │
│                   │                      │                      │
│                   │  Tools   ✅ 已实现    │ ← 本项目的核心       │
│                   │  Resources ❌ 计划中  │                      │
│                   │  Prompts  ❌ 计划中   │                      │
│                   └─────────────────────┘                      │
└────────────────────────────────────────────────────────────────┘
```

---

## 2. MCP 协议的三种原语

MCP 规范定义了三种服务器能力（原语），本项目的使用状态：

| 原语 | 说明 | 本项目状态 | 用途 |
|---|---|---|---|
| **Tools** | LLM 可调用的函数（Function Calling） | ✅ 已实现 15 个 | 检索、导入、问答、管理 |
| **Resources** | 暴露给 LLM 的上下文数据 | ❌ 未实现 | 未来：暴露文档内容给 LLM 读取 |
| **Prompts** | 可复用的提示词模板 | ❌ 未实现 | 未来：暴露提示词模板给 LLM 选用 |

当前 RAG-MCP 是一个 **纯 Tools 型 MCP 服务器**。

---

## 3. 传输层

### 3.1 支持的传输方式

RAG-MCP 支持三种 MCP 传输方式：

| 传输方式 | 原理 | 适用场景 | 推荐度 |
|---|---|---|---|
| **Streamable HTTP** | HTTP + SSE 流式响应，支持远程访问 | 生产部署、远程 Agent 接入 | ⭐ 推荐 |
| **Stdio** | 客户端 spawn 子进程，通过 stdin/stdout 通信 | 本地开发、桌面应用 | ✅ 通用 |
| **SSE** | HTTP Server-Sent Events（旧版） | 兼容旧版 MCP Client | ⚠️ 兼容 |

通过 `config/settings.yaml` 中的 `mcp.transport` 配置选择传输方式。

### 3.2 Streamable HTTP 模式（推荐）

**Streamable HTTP** 是 MCP 官方新一代 HTTP 传输协议，支持远程客户端通过网络访问 MCP 服务。

```
┌──────────────────┐       HTTP POST/SSE       ┌──────────────────────┐
│  MCP Client      │◄─────────────────────────►│  RAG-MCP Server      │
│  (远程 Agent)    │   http://host:port/mcp     │  (FastAPI + MCP)     │
│                  │                            │                      │
│  1. POST /mcp    │── initialize ────────────▶ │  握手 + 能力声明     │
│  2. POST /mcp    │── tools/list ────────────▶ │  返回 15 个工具      │
│  3. POST /mcp    │── tools/call ────────────▶ │  执行 Use Case       │
│                  │◀── SSE stream result ─────  │  流式返回结果        │
└──────────────────┘                            └──────────────────────┘
```

优势：
- **远程访问** — 不限于本地进程，支持网络部署
- **与 REST API 共存** — MCP 挂载在 `/mcp`，REST 在 `/api/v1/*`
- **流式响应** — 支持 SSE 流式输出，适合长时间操作
- **生产就绪** — 可部署在 Docker/K8s 环境

启动方式：

```bash
# 方式一：统一服务（REST API + MCP HTTP 共存）
PYTHONPATH=backend/src uvicorn rag_mcp.main:app --host 0.0.0.0 --port 8000

# 方式二：独立 MCP HTTP 服务
python -m rag_mcp.mcp.server --transport streamable-http
```

### 3.3 Stdio 模式

Stdio 模式下，LLM 客户端（如 Claude Desktop）直接启动 `python -m rag_mcp.mcp.server` 作为子进程，通过标准输入/输出交换 JSON-RPC 消息。

```
┌──────────────────┐                    ┌──────────────────────┐
│  Claude Desktop  │   stdin/stdout     │  RAG-MCP Server      │
│  (父进程)        │◄──────────────────►│  (子进程)             │
│                  │   JSON-RPC 消息    │                      │
│  用户提问        │                    │  python -m            │
│  ↓               │                    │  rag_mcp.mcp.server   │
│  LLM 决定调工具  │── tools/call ────▶ │  执行 Use Case        │
│  ↓               │◀── tool result ──  │  返回结果             │
│  组织自然语言回复 │                    │                      │
└──────────────────┘                    └──────────────────────┘
```

```bash
# stdio 模式
python -m rag_mcp.mcp.server --transport stdio
```

### 3.2 通信协议

MCP 使用 **JSON-RPC 2.0** 格式：

```json
// 客户端 → 服务器：初始化握手
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-06-18",
    "clientInfo": { "name": "claude-desktop", "version": "1.0" }
  }
}

// 服务器 → 客户端：返回能力声明
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-06-18",
    "capabilities": { "tools": {} },
    "serverInfo": { "name": "rag-mcp", "version": "0.1.0" }
  }
}
```

```json
// 客户端 → 服务器：列出可用工具
{ "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {} }

// 服务器 → 客户端：返回 15 个工具定义
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "knowledge_query",
        "description": "Run hybrid retrieval over the active knowledge base.",
        "inputSchema": {
          "type": "object",
          "properties": {
            "query": { "type": "string", "minLength": 1 },
            "top_k": { "type": "integer", "minimum": 1, "maximum": 20, "default": 5 }
          },
          "required": ["query"]
        }
      },
      // ... 另外 14 个工具
    ]
  }
}
```

```json
// 客户端 → 服务器：调用工具
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "knowledge_query",
    "arguments": { "query": "什么是混合检索", "top_k": 5 }
  }
}

// 服务器 → 客户端：返回结构化结果
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [{ "type": "text", "text": "{\"results\": [...]}" }],
    "structuredContent": {
      "query": "什么是混合检索",
      "results": [
        {
          "chunk_id": "...",
          "score": 0.92,
          "text": "混合检索结合了稠密向量检索和稀疏关键词检索...",
          "retrieval_method": "dense+sparse+rerank"
        }
      ],
      "trace_id": "abc123"
    },
    "isError": false
  }
}
```

---

## 4. MCP 服务器实现架构

### 4.1 文件结构

```
mcp/
├── __init__.py          # 模块标记
├── sdk_server.py        # 核心：FastMCP 构建、工具注册、多传输支持
├── protocol.py          # 兼容层：JSON-RPC + Legacy 双格式适配
└── server.py            # 入口：python -m rag_mcp.mcp.server [--transport ...]
```

### 4.2 三层实现

```
┌───────────────────────────────────────────────────────────────┐
│  server.py     入口层                                         │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  python -m rag_mcp.mcp.server --transport <transport> │    │
│  │      │                                                │    │
│  │      └── sdk_server.main(transport)                   │    │
│  │              ├─ FastMCP.run(transport="streamable-http")│   │
│  │              ├─ FastMCP.run(transport="sse")           │    │
│  │              └─ FastMCP.run(transport="stdio")         │    │
│  └───────────────────────────────────────────────────────┘    │
│                          │                                    │
│  sdk_server.py  工具层   │                                    │
│  ┌───────────────────────┼───────────────────────────────┐    │
│  │  15 个工具函数         │                               │    │
│  │  ┌────────────────────┼──────────────────┐           │    │
│  │  │ knowledge_query(query, top_k)          │           │    │
│  │  │   │                                    │           │    │
│  │  │   └─ get_container()                   │           │    │
│  │  │       .query_use_case.execute(...)     │           │    │
│  │  └────────────────────────────────────────┘           │    │
│  │                                                       │    │
│  │  _build_fastmcp_server()                              │    │
│  │    ├─ FastMCP(name="rag-mcp")                         │    │
│  │    └─ for tool in SDK_TOOLS:                          │    │
│  │         server.add_tool(tool, structured_output=True) │    │
│  └───────────────────────────────────────────────────────┘    │
│                          │                                    │
│  main.py       集成层   │（FastAPI + MCP HTTP 共存）           │
│  ┌───────────────────────┼───────────────────────────────┐    │
│  │  create_app()                                        │    │
│  │    ├─ FastAPI() ← REST API /api/v1/*                  │    │
│  │    └─ app.mount("/mcp", streamable_http_app())        │    │
│  │         └─ MCP Streamable HTTP 传输                   │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                               │
│  protocol.py    兼容层                                        │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  handle_message()                                     │    │
│  │    ├─ {"tool": ...}  → _handle_legacy_tool_message()  │    │
│  │    └─ {"jsonrpc": "2.0", "method": ...}               │    │
│  │         ├─ "initialize"      → 握手 + 能力声明         │    │
│  │         ├─ "tools/list"      → 返回工具列表            │    │
│  │         └─ "tools/call"      → 执行工具               │    │
│  └───────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────┘
```

### 4.3 工具 Schema 自动生成

FastMCP 从 Python 函数签名自动生成 MCP 工具 Schema：

```python
# Python 代码
TopK = Annotated[int, Field(ge=1, le=20)]

def knowledge_query(
    query: Annotated[str, Field(min_length=1)],
    top_k: TopK = 5,
) -> QueryResponse:
    """Run hybrid retrieval over the active knowledge base."""
    ...
```

自动映射为：

```json
{
  "name": "knowledge_query",
  "description": "Run hybrid retrieval over the active knowledge base.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "minLength": 1
      },
      "top_k": {
        "type": "integer",
        "minimum": 1,
        "maximum": 20,
        "default": 5
      }
    },
    "required": ["query"]
  }
}
```

**关键点**：`structured_output=True` 让 FastMCP 把 `QueryResponse`（Pydantic 模型）序列化为 `structuredContent`，LLM 客户端可以精确解析返回值结构。

---

## 5. 兼容层：双格式支持

`protocol.py` 提供向后兼容，同时支持两种消息格式：

```
handle_message(msg)
     │
     ├── msg 有 "tool" 字段？
     │   └── Yes → Legacy 格式处理
     │         {"tool": "knowledge_query", "arguments": {"query": "hello"}}
     │         返回: {"ok": true, "data": {...}}
     │         或:   {"ok": false, "error": "..."}
     │
     └── msg 有 "jsonrpc":"2.0" + "method" 字段？
         └── Yes → JSON-RPC 格式处理
               {"jsonrpc": "2.0", "method": "tools/call", "params": {...}}
               返回: {"jsonrpc": "2.0", "result": {...}}
               或:   {"jsonrpc": "2.0", "error": {...}}
```

**为什么保留兼容层？**

- 旧版测试用例使用 Legacy JSON 格式
- 过渡期 SDK 和 Legacy 共存
- 计划在 P2 阶段移除（见 [roadmap.md](../roadmap.md)）

---

## 6. 15 个工具完整清单

### 6.1 核心检索（4 个）

| 工具 | 参数 | 说明 |
|---|---|---|
| `knowledge_ingest` | `path: str`, `force_rebuild: bool` | 导入文档（支持 .txt/.md/.pdf） |
| `knowledge_query` | `query: str`, `top_k: int (1-20)` | 混合检索（Dense+Sparse+RRF+Rerank） |
| `generate_answer` | `query: str`, `top_k: int (1-20)` | 检索 + LLM 生成回答（含引用来源） |
| `knowledge_status` | *(无)* | 知识库总览（文档数、分块数、索引状态） |

### 6.2 文档管理（4 个）

| 工具 | 参数 | 说明 |
|---|---|---|
| `list_documents` | *(无)* | 列出所有已导入文档 |
| `get_document_detail` | `document_id: str` | 文档详情（含每个分块内容） |
| `get_document_summary` | `document_id: str` | 文档摘要（关键统计） |
| `delete_document` | `document_id: str` | 删除文档及全部索引 |

### 6.3 索引运维（2 个）

| 工具 | 参数 | 说明 |
|---|---|---|
| `list_collections` | *(无)* | 列出 Collection 及统计 |
| `rebuild_collection` | `collection_name: str?` | 从源文档重建索引 |

### 6.4 评估（3 个）

| 工具 | 参数 | 说明 |
|---|---|---|
| `run_evaluation` | `dataset_path: str?`, `top_k: int?` | 运行 Hit Rate / MRR 评估 |
| `list_evaluation_reports` | `limit: int (1-100)` | 列出评估报告 |
| `get_evaluation_report` | `report_id: str` | 获取单个报告详情 |

### 6.5 可观测性（2 个）

| 工具 | 参数 | 说明 |
|---|---|---|
| `list_traces` | `trace_type: str?`, `limit: int (1-100)` | 列出调用追踪 |
| `get_trace_detail` | `trace_id: str` | 获取追踪详情（含每阶段耗时） |

---

## 7. 错误处理

MCP 层的错误处理遵循 JSON-RPC 2.0 规范：

```
Use Case 抛出异常
     │
     ├── NotFoundError         → {"isError": true, "content": "Not found: ..."}
     ├── IngestionError        → {"isError": true, "content": "Ingestion failed: ..."}
     ├── ProviderError         → {"isError": true, "content": "API call failed: ..."}
     ├── ConfigurationError    → JSON-RPC error -32000
     └── 未知异常               → JSON-RPC error -32603 (Internal error)
```

LLM 客户端收到 `isError: true` 后，会将错误信息反馈给用户或重试。

---

## 8. 客户端配置指南

### Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）或 `%APPDATA%\Claude\claude_desktop_config.json`（Windows）：

```json
{
  "mcpServers": {
    "rag-mcp": {
      "command": "python",
      "args": ["-m", "rag_mcp.mcp.server"],
      "cwd": "/path/to/RAG-MCP/backend",
      "env": {
        "ZHIPU_API_KEY": "your-key",
        "DEEPSEEK_API_KEY": "your-key"
      }
    }
  }
}
```

### Cursor

Settings → MCP → Add Server：

```json
{
  "mcpServers": {
    "rag-mcp": {
      "command": "python",
      "args": ["-m", "rag_mcp.mcp.server"],
      "cwd": "/path/to/RAG-MCP/backend"
    }
  }
}
```

### Python 编程调用（stdio）

```python
import asyncio
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

async def main():
    server = StdioServerParameters(
        command="python",
        args=["-m", "rag_mcp.mcp.server"],
        cwd="/path/to/RAG-MCP/backend",
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 列出工具
            tools = await session.list_tools()
            for t in tools.tools:
                print(f"  {t.name}: {t.description}")

            # 查询知识库
            result = await session.call_tool(
                "knowledge_query",
                arguments={"query": "什么是 RAG", "top_k": 3},
            )
            print(result.structuredContent)

asyncio.run(main())
```

### Python 编程调用（Streamable HTTP）

```python
import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    url = "http://127.0.0.1:8000/mcp"
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 列出工具
            tools = await session.list_tools()

            # 查询知识库
            result = await session.call_tool(
                "knowledge_query",
                arguments={"query": "什么是 RAG", "top_k": 3},
            )
            print(result.structuredContent)

asyncio.run(main())
```

---

## 9. 未来规划：Resources & Prompts

根据 [roadmap.md](../roadmap.md)，计划在 P2 阶段扩展 MCP 能力：

| 原语 | 计划用途 | 示例 |
|---|---|---|
| **Resources** | 暴露文档内容供 LLM 直接读取 | `rag-mcp://documents/{id}/content` |
| **Prompts** | 暴露提示词模板供 LLM 选用 | `rag-mcp://prompts/answer_with_citations` |

当前 capabilities 声明中只有 `"tools": {}`，未来将扩展为：

```json
{
  "capabilities": {
    "tools": {},
    "resources": { "subscribe": true },
    "prompts": { "listChanged": true }
  }
}
```
