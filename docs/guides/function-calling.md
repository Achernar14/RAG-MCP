# Function Calling — MCP 工具调用机制详解

## 1. 什么是 Function Calling

Function Calling（函数调用）是 LLM 与外部系统交互的标准方式。LLM 不再只能"说话"，而是可以**调用工具**来完成实际任务。

RAG-MCP 通过 **MCP（Model Context Protocol）** 协议暴露 Function Calling 能力。任何支持 MCP 的 LLM 客户端（Claude Desktop、Cursor、Continue 等）都可以直接调用本项目的 15 个工具，完成知识库的导入、检索、问答等操作。

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Function Calling 完整链路                        │
│                                                                     │
│   用户: "帮我查一下知识库里有哪些文档"                                │
│     │                                                               │
│     ▼                                                               │
│   ┌──────────┐    tools/list     ┌────────────────────────┐         │
│   │  LLM     │ ───────────────▶ │  RAG-MCP MCP Server     │         │
│   │  Client  │ ◀─────────────── │  (15 个工具)             │         │
│   │          │   tool schema    │                          │         │
│   │          │                   │                          │         │
│   │          │   tools/call     │                          │         │
│   │          │ ───────────────▶ │  list_documents()        │         │
│   │          │ ◀─────────────── │  → 返回文档列表           │         │
│   └──────────┘   tool result    └────────────────────────┘         │
│     │                                                               │
│     ▼                                                               │
│   用户看到: "知识库中有 3 个文档: ..."                                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 双层接入：REST API + MCP Tools

本项目通过**两个并列的接入层**暴露相同的能力：

```
                        ┌──────────────────────┐
                        │   Use Case 层        │
                        │  (15 个 Use Case)    │
                        │                      │
                        │  QueryKnowledge      │
                        │  IngestDocument      │
                        │  GenerateAnswer      │
                        │  ...                 │
                        └──────┬───────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
          ┌─────────▼──────┐    ┌─────────▼──────────┐
          │  REST API      │    │  MCP Server         │
          │  (FastAPI)     │    │  (FastMCP + stdio)  │
          │                │    │                     │
          │  POST /ingest  │    │  knowledge_ingest   │
          │  POST /query   │    │  knowledge_query    │
          │  ...           │    │  ...                │
          └────────────────┘    └─────────────────────┘
           HTTP 客户端用          LLM 客户端用
```

| 对比维度 | REST API | MCP Tools |
|---|---|---|
| 协议 | HTTP/JSON | MCP JSON-RPC over stdio |
| 客户端 | curl、Postman、前端应用 | Claude Desktop、Cursor、任意 MCP 客户端 |
| 入口 | `uvicorn rag_mcp.main:app` | `python -m rag_mcp.mcp.server` |
| 传输 | 网络 TCP | 标准输入/输出（进程间通信） |
| Schema 定义 | Pydantic 模型 | 函数签名 + `Annotated` 类型 |
| 业务逻辑 | **同一个 Use Case 层** | **同一个 Use Case 层** |

---

## 3. MCP 工具注册机制

### 3.1 从 Python 函数到 MCP Tool

核心文件：[sdk_server.py](../../backend/src/rag_mcp/mcp/sdk_server.py)

一个 MCP Tool 就是一个**带类型注解的普通 Python 函数**：

```python
from typing import Annotated
from pydantic import Field

TopK = Annotated[int, Field(ge=1, le=20)]

def knowledge_query(
    query: Annotated[str, Field(min_length=1)],
    top_k: TopK = 5,
) -> QueryResponse:
    """Run hybrid retrieval over the active knowledge base."""
    return get_container().query_use_case.execute(
        QueryRequest(query=query, top_k=top_k)
    )
```

FastMCP 自动从这个函数提取三要素：

```
┌─────────────────────────────────────────────────────────────────┐
│  Python 函数                  MCP Tool Schema                    │
│                                                                 │
│  函数名 knowledge_query   →  tool name: "knowledge_query"       │
│                                                                 │
│  参数签名:                 →  inputSchema:                      │
│    query: str (min 1)        {                                   │
│    top_k: int (1-20)           "query": {                        │
│                                  "type": "string",               │
│                                  "minLength": 1                  │
│                                },                                │
│                                "top_k": {                        │
│                                  "type": "integer",              │
│                                  "minimum": 1,                   │
│                                  "maximum": 20,                  │
│                                  "default": 5                    │
│                                }                                 │
│                              }                                   │
│                                                                 │
│  返回类型 QueryResponse   →  outputSchema: (Pydantic → JSON)    │
│                                                                 │
│  docstring                →  description:                       │
│    "Run hybrid retrieval     "Run hybrid retrieval over the     │
│     over the active           active knowledge base."           │
│     knowledge base."                                           │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 注册流程

```python
# 1. 收集所有工具函数
SDK_TOOLS = [
    knowledge_query,
    generate_answer,
    knowledge_ingest,
    # ... 共 15 个
]

# 2. 构建 FastMCP Server 并逐个注册
def _build_fastmcp_server() -> FastMCP:
    server = FastMCP(name="rag-mcp")
    server._mcp_server.version = "0.1.0"
    for tool in SDK_TOOLS:
        server.add_tool(tool, name=tool.__name__, structured_output=True)
    return server

# 3. 缓存为单例
@lru_cache(maxsize=1)
def create_fastmcp_server() -> FastMCP:
    return _build_fastmcp_server()

# 4. 启动 stdio 传输
def main() -> int:
    create_fastmcp_server().run(transport="stdio")
    return 0
```

**`structured_output=True`** 是关键参数 — 它让 FastMCP 把 Pydantic 返回对象序列化为结构化 JSON 而非纯文本，LLM 客户端可以精确解析返回值。

---

## 4. 15 个工具完整目录

### 4.1 知识库核心（Core RAG）

| 工具名 | 功能 | 输入 | 返回 |
|---|---|---|---|
| `knowledge_ingest` | 导入文档到知识库 | `path: str`, `force_rebuild: bool` | 文档 ID、分块数、耗时 |
| `knowledge_query` | 混合检索 | `query: str`, `top_k: int (1-20)` | 检索结果列表（含分数、文本、方法） |
| `generate_answer` | 检索 + LLM 生成回答 | `query: str`, `top_k: int (1-20)` | 回答文本 + 引用来源 + trace_id |
| `knowledge_status` | 知识库总览 | *(无参数)* | 文档数、分块数、索引状态 |

### 4.2 文档管理（Document Management）

| 工具名 | 功能 | 输入 | 返回 |
|---|---|---|---|
| `list_documents` | 列出所有文档 | *(无参数)* | 文档列表（ID、文件名、状态） |
| `get_document_detail` | 文档详情（含分块） | `document_id: str` | 完整元数据 + 各分块内容 |
| `get_document_summary` | 文档摘要 | `document_id: str` | 关键统计信息 |
| `delete_document` | 删除文档及索引 | `document_id: str` | 删除确认 + 清理的向量数 |

### 4.3 索引运维（Index Operations）

| 工具名 | 功能 | 输入 | 返回 |
|---|---|---|---|
| `list_collections` | 列出 Collection | *(无参数)* | Collection 名称、文档数、分块数 |
| `rebuild_collection` | 从源文档重建索引 | `collection_name: str?` | 重建结果、耗时 |

### 4.4 评估（Evaluation）

| 工具名 | 功能 | 输入 | 返回 |
|---|---|---|---|
| `run_evaluation` | 运行评估 | `dataset_path: str?`, `top_k: int?` | Hit Rate、MRR、逐条详情 |
| `list_evaluation_reports` | 列出评估报告 | `limit: int (1-100)` | 报告列表 |
| `get_evaluation_report` | 获取单个报告 | `report_id: str` | 完整报告内容 |

### 4.5 可观测性（Observability）

| 工具名 | 功能 | 输入 | 返回 |
|---|---|---|---|
| `list_traces` | 列出调用追踪 | `trace_type: str?`, `limit: int (1-100)` | Trace 列表 |
| `get_trace_detail` | 获取单条追踪 | `trace_id: str` | 完整追踪（含每阶段耗时） |

---

## 5. 一次完整的 Function Call 流程

以用户问 "RAG 系统如何处理 PDF 文件？" 为例：

```
[客户端] Claude Desktop / Cursor / 任意 MCP Client
   │
   │  1. 启动时: 客户端 spawn RAG-MCP 进程
   │     python -m rag_mcp.mcp.server
   │
   │  2. 初始化: 客户端发送 initialize 请求
   │     → RAG-MCP 返回 server info + capabilities
   │
   │  3. 发现工具: 客户端发送 tools/list
   │     → RAG-MCP 返回 15 个工具的 schema
   │
   │  4. 用户提问 → LLM 决定调用 generate_answer
   │
   │  5. 客户端发送 tools/call:
   │     {
   │       "method": "tools/call",
   │       "params": {
   │         "name": "generate_answer",
   │         "arguments": {
   │           "query": "RAG 系统如何处理 PDF 文件？",
   │           "top_k": 5
   │         }
   │       }
   │     }
   │
   ▼
[RAG-MCP 内部]
   │
   │  6. FastMCP 找到 generate_answer 函数
   │  7. 验证参数 (query 非空, top_k 1-20)
   │  8. 调用 Use Case 层:
   │     generate_answer_use_case.execute(...)
   │       │
   │       ├── 5a. Query Embedding (Zhipu API)
   │       ├── 5b. Dense Retrieval (Weaviate)
   │       ├── 5c. Sparse Retrieval (BM25)
   │       ├── 5d. RRF Fusion
   │       ├── 5e. Lexical Rerank
   │       ├── 5f. Prompt 构建
   │       └── 5g. LLM 生成回答 (DeepSeek API)
   │
   │  9. 返回 Pydantic DTO → 序列化为 JSON
   │
   ▼
[客户端]
   │
   │  10. LLM 拿到工具返回结果:
   │      {
   │        "answer": "RAG-MCP 通过 PdfDocumentLoader...",
   │        "sources": [{ "chunk_id": "...", "text": "...", "score": 0.92 }],
   │        "trace_id": "abc123"
   │      }
   │
   │  11. LLM 基于工具结果组织自然语言回复给用户
   │
   ▼
  用户看到完整的回答，附带引用来源
```

---

## 6. 向后兼容的协议层

核心文件：[protocol.py](../../backend/src/rag_mcp/mcp/protocol.py)

除了标准的 MCP JSON-RPC 协议，项目还兼容两种旧格式：

### 6.1 标准 MCP JSON-RPC

```json
// 请求
{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
 "params": {"name": "knowledge_query", "arguments": {"query": "hello"}}}

// 响应
{"jsonrpc": "2.0", "id": 1, "result": {
  "content": [{"type": "text", "text": "{...}"}],
  "structuredContent": {"results": [...], "trace_id": "..."},
  "isError": false
}}
```

### 6.2 Legacy JSON 格式

```json
// 请求
{"tool": "knowledge_query", "arguments": {"query": "hello"}}

// 响应
{"ok": true, "data": {"results": [...], "trace_id": "..."}}
```

### 6.3 支持的 JSON-RPC 方法

| 方法 | 说明 |
|---|---|
| `initialize` | 握手，返回服务器能力声明 |
| `notifications/initialized` | 客户端确认初始化完成（无响应） |
| `tools/list` | 返回所有工具定义 |
| `tools/call` | 调用指定工具 |

---

## 7. 如何在 LLM 客户端中使用

### 7.1 Claude Desktop 配置

编辑 `claude_desktop_config.json`：

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

### 7.2 Cursor 配置

在 Cursor 设置中添加 MCP Server：

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

### 7.3 编程方式调用

```python
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters

server_params = StdioServerParameters(
    command="python",
    args=["-m", "rag_mcp.mcp.server"],
    cwd="/path/to/RAG-MCP/backend",
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # 列出所有工具
        tools = await session.list_tools()
        print(f"Available tools: {[t.name for t in tools.tools]}")

        # 调用工具
        result = await session.call_tool(
            "knowledge_query",
            arguments={"query": "什么是 RAG", "top_k": 3},
        )
        print(result)
```

---

## 8. 工具调用时序图

```
LLM Client                MCP SDK              Use Case              Infrastructure
    │                        │                     │                       │
    │  tools/list            │                     │                       │
    │───────────────────────▶│                     │                       │
    │  15 tool schemas       │                     │                       │
    │◀───────────────────────│                     │                       │
    │                        │                     │                       │
    │  tools/call            │                     │                       │
    │  name: knowledge_ingest│                     │                       │
    │  args: {path: "x.pdf"} │                     │                       │
    │───────────────────────▶│                     │                       │
    │                        │  execute()           │                       │
    │                        │────────────────────▶│                       │
    │                        │                     │  validate source      │
    │                        │                     │──────────────────────▶│
    │                        │                     │  load document        │
    │                        │                     │──────────────────────▶│
    │                        │                     │  split into chunks    │
    │                        │                     │──────────────────────▶│
    │                        │                     │  embed texts          │
    │                        │                     │──────────────────────▶│
    │                        │                     │  upsert to Weaviate   │
    │                        │                     │──────────────────────▶│
    │                        │                     │  upsert to BM25       │
    │                        │                     │──────────────────────▶│
    │                        │  IngestResponse      │                       │
    │                        │◀────────────────────│                       │
    │  structured result     │                     │                       │
    │◀───────────────────────│                     │                       │
    │                        │                     │                       │
```

---

## 9. 错误处理

```
┌─────────────────────────────────────────────────────────────────┐
│  错误传播链路                                                    │
│                                                                 │
│  Infrastructure 层                                              │
│    ProviderError("Zhipu embedding request failed: timeout")     │
│         │                                                       │
│         ▼                                                       │
│  Use Case 层                                                    │
│    异常向上传播                                                  │
│         │                                                       │
│         ▼                                                       │
│  MCP SDK 层 (FastMCP)                                           │
│    捕获为 ToolError                                              │
│         │                                                       │
│         ▼                                                       │
│  协议层 (protocol.py)                                           │
│    ├─ JSON-RPC: {"isError": true, "content": [error text]}      │
│    └─ Legacy:   {"ok": false, "error": "error message"}        │
│                                                                 │
│  特定错误:                                                      │
│    NotFoundError → 找不到文档/Trace/报告                         │
│    IngestionError → 文件不支持/过大/读取失败                      │
│    ConfigurationError → 缺少 API Key/配置错误                    │
│    ProviderError → 外部服务调用失败                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. 扩展指南：添加新工具

### Step 1：创建 Use Case

```python
# application/use_cases/my_new_use_case.py
class MyNewUseCase:
    def __init__(self, some_dependency): ...)

    def execute(self, request: MyRequest) -> MyResponse:
        # 业务逻辑
        return MyResponse(...)
```

### Step 2：注册到 DTO

```python
# application/dto/models.py
class MyRequest(BaseModel):
    param: str

class MyResponse(BaseModel):
    result: str
```

### Step 3：注册到 DI 容器

```python
# core/container.py
self.my_new_use_case = MyNewUseCase(dependency=...)
```

### Step 4：添加 MCP Tool 函数

```python
# mcp/sdk_server.py
def my_new_tool(
    param: Annotated[str, Field(min_length=1)],
) -> MyResponse:
    """Description that the LLM will see."""
    return get_container().my_new_use_case.execute(MyRequest(param=param))

# 加入 SDK_TOOLS 列表
SDK_TOOLS = [
    # ...existing tools
    my_new_tool,
]
```

### Step 5（可选）：添加 REST API 路由

```python
# api/v1/routes.py
@router.post("/my-new-endpoint")
def my_new_endpoint(request: MyRequest) -> dict:
    response = get_container().my_new_use_case.execute(request)
    return {"code": 0, "message": "ok", "data": response.model_dump()}
```

---

## 11. 关键代码位置速查

| 关注点 | 文件 |
|---|---|
| MCP 工具定义（15 个函数） | `mcp/sdk_server.py` |
| 协议兼容层（JSON-RPC + Legacy） | `mcp/protocol.py` |
| CLI 启动入口 | `mcp/server.py` |
| REST API 路由 | `api/v1/routes.py` |
| 请求/响应 DTO | `application/dto/models.py` |
| DI 容器（Use Case 接线） | `core/container.py` |
| 输入/输出 Schema | 由 `Annotated[type, Field(...)]` 自动生成 |
