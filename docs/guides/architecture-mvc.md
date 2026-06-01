# 架构设计解析 — Clean Architecture 与分层模式

## 1. 这个项目是 MVC 吗？

**严格来说不是 MVC，而是 Clean Architecture（整洁架构）。**

MVC 将应用分为 Model-View-Controller 三层，而 RAG-MCP 的分层更细致：

```
┌─────────────────────────────────────────────────────────────────┐
│  MVC 三层                        本项目实际分层                  │
│                                                                 │
│  ┌──────────┐                   ┌──────────────────────────┐   │
│  │  View    │  ←── 对应 ──→     │  Presentation            │   │
│  │  (视图)  │                   │  ├─ REST API (FastAPI)    │   │
│  │          │                   │  └─ MCP Tools (FastMCP)   │   │
│  └──────────┘                   └──────────────────────────┘   │
│                                                                 │
│  ┌──────────┐                   ┌──────────────────────────┐   │
│  │Controller│  ←── 对应 ──→     │  Application              │   │
│  │  (控制器)│                   │  ├─ 15 Use Cases          │   │
│  │          │                   │  └─ 25+ DTOs              │   │
│  └──────────┘                   └──────────────────────────┘   │
│                                                                 │
│  ┌──────────┐                   ┌──────────────────────────┐   │
│  │  Model   │  ←── 对应 ──→     │  Domain                   │   │
│  │  (模型)  │                   │  ├─ Entities (9 个)       │   │
│  │          │                   │  ├─ Contracts (7 个接口)  │   │
│  │          │                   │  └─ Services (3 个)       │   │
│  └──────────┘                   └──────────────────────────┘   │
│                                                                 │
│                                  ┌──────────────────────────┐   │
│                  (MVC 没有这层)   │  Infrastructure           │   │
│                                  │  ├─ 向量存储              │   │
│                                  │  ├─ Embedding / LLM       │   │
│                                  │  ├─ 文件加载/分块          │   │
│                                  │  └─ JSON/Redis 持久化      │   │
│                                  └──────────────────────────┘   │
│                                                                 │
│                                  ┌──────────────────────────┐   │
│                  (MVC 没有这层)   │  Core                     │   │
│                                  │  ├─ Settings 配置         │   │
│                                  │  ├─ Container DI 容器     │   │
│                                  │  ├─ Exceptions 异常体系    │   │
│                                  │  └─ Tracing 可观测性       │   │
│                                  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 为什么不用 MVC？

MVC 适合 **UI 驱动** 的应用（Web 页面、桌面软件）。但 RAG-MCP 是一个 **后端服务**，它面临的问题 MVC 解决不了：

| 问题 | MVC 怎么做 | Clean Architecture 怎么做 |
|---|---|---|
| 多种接入方式（REST + MCP + Dashboard） | Controller 膨胀，if-else 切换 | Presentation 层可自由扩展，业务逻辑不变 |
| 可替换的外部服务（Embedding/LLM/向量库） | Model 层耦合具体实现 | Domain 定义接口，Infrastructure 提供实现 |
| 依赖注入（15 个 Use Case 需要大量依赖） | 无标准做法 | Container 作为组合根统一接线 |
| 业务逻辑与技术实现分离 | 边界模糊 | 依赖方向严格：外层→内层，绝不反转 |

---

## 2. 分层架构全景

```
                          依赖方向 →→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→→
                          内层不知道外层的存在。外层依赖内层。绝不反向依赖。

┌───────────────────────────────────────────────────────────────────────────┐
│                                                                           │
│    ┌─────────────────────────────────────────────────────────────────┐   │
│    │  Presentation (展示层)                                         │   │
│    │                                                                 │   │
│    │  ┌───────────────────┐  ┌───────────────────┐                  │   │
│    │  │  api/v1/routes.py │  │  mcp/sdk_server.py │                  │   │
│    │  │  REST API 16 路由  │  │  MCP 15 工具       │                  │   │
│    │  └────────┬──────────┘  └────────┬──────────┘                  │   │
│    │           │                      │                              │   │
│    └───────────┼──────────────────────┼──────────────────────────────┘   │
│                │                      │                                  │
│                ▼                      ▼                                  │
│    ┌─────────────────────────────────────────────────────────────────┐   │
│    │  Application (应用层 / Use Cases)                              │   │
│    │                                                                 │   │
│    │  ┌─────────────────────────────────────────────────────────┐   │   │
│    │  │  application/use_cases/  (15 个用例)                    │   │   │
│    │  │  application/dto/models.py  (25+ 个 DTO)                │   │   │
│    │  └────────────────────────┬────────────────────────────────┘   │   │
│    │                           │                                     │   │
│    └───────────────────────────┼─────────────────────────────────────┘   │
│                                │                                         │
│               ┌────────────────┼────────────────┐                       │
│               ▼                ▼                ▼                       │
│    ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐         │
│    │  Domain       │  │  Domain       │  │  Core                │         │
│    │  Entities     │  │  Services     │  │  Settings            │         │
│    │  (数据模型)    │  │  (业务算法)    │  │  Container (DI)      │         │
│    │  Contracts    │  │              │  │  Exceptions           │         │
│    │  (抽象接口)    │  │              │  │  Tracing              │         │
│    └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘         │
│           │                 │                      │                     │
│           └────────┬────────┘──────────────────────┘                     │
│                    ▼                                                      │
│    ┌─────────────────────────────────────────────────────────────────┐   │
│    │  Infrastructure (基础设施层 / 具体实现)                         │   │
│    │                                                                 │   │
│    │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │   │
│    │  │ Embedding│ │   LLM    │ │  Vector  │ │  Loaders │          │   │
│    │  │ Zhipu    │ │DeepSeek  │ │ Weaviate │ │ PDF/TXT  │          │   │
│    │  │ Hash     │ │  Stub    │ │ Chroma   │ │ Compound │          │   │
│    │  └──────────┘ └──────────┘ │ Memory   │ └──────────┘          │   │
│    │  ┌──────────┐ ┌──────────┐ └──────────┘ ┌──────────┐          │   │
│    │  │ Splitters│ │  BM25    │ ┌──────────┐ │ Reranker │          │   │
│    │  │  Simple  │ │  Sparse  │ │  Repos   │ │ Lexical  │          │   │
│    │  └──────────┘ └──────────┘ │  JSON    │ └──────────┘          │   │
│    │  ┌──────────┐ ┌──────────┐ │  Memory  │ ┌──────────┐          │   │
│    │  │ Pipeline │ │  Redis   │ └──────────┘ │ Prompts  │          │   │
│    │  │ Ingest   │ │  Cache   │              │ Templates│          │   │
│    │  └──────────┘ └──────────┘              └──────────┘          │   │
│    └─────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 每一层详解

### 3.1 Domain 层（领域层 — 最内层）

**位置**：`domain/`

**职责**：定义业务核心 — 数据是什么、接口长什么样、算法怎么算。

**关键规则**：**零外部依赖**。不导入 infrastructure、不导入 application、不导入任何框架。

```
domain/
├── entities/
│   └── models.py          # 9 个纯数据类（@dataclass）
│                           # Document, Chunk, ChunkRecord,
│                           # RetrievalResult, SourceTrace,
│                           # EvaluationCase, ...
│
├── repositories/
│   └── contracts.py        # 7 个抽象接口（ABC）
│                           # EmbeddingProvider    — 怎么生成向量
│                           # LlmProvider          — 怎么调 LLM
│                           # VectorStoreRepository — 怎么存/查向量
│                           # DocumentRepository   — 怎么存文档
│                           # ChunkRepository      — 怎么存分块
│                           # SparseIndexRepository — 怎么做稀疏检索
│                           # EvaluationReportRepository
│
└── services/
    ├── retrieval.py         # 纯 Dense 检索服务
    ├── hybrid_retrieval.py  # Dense + Sparse + RRF 融合（核心算法）
    └── reranking.py         # BaseReranker 抽象基类
```

**设计意图**：

```python
# Domain 定义"我需要什么"（接口/契约）
class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

# Infrastructure 提供"具体怎么做"（实现）
class ZhipuEmbeddingProvider(EmbeddingProvider):
    def embed_texts(self, texts):  # 调 Zhipu API
        ...

class HashEmbeddingProvider(EmbeddingProvider):
    def embed_texts(self, texts):  # 本地 SHA-256 哈希
        ...
```

这叫做 **依赖倒置（Dependency Inversion）** — 内层定义接口，外层实现接口。

### 3.2 Application 层（应用层 — 编排层）

**位置**：`application/`

**职责**：编排业务流程。每个 Use Case 代表一个完整的用户操作。

```
application/
├── dto/
│   └── models.py           # 25+ 个 Pydantic 请求/响应模型
│                            # IngestRequest → IngestResponse
│                            # QueryRequest  → QueryResponse
│                            # GenerateAnswerRequest → GenerateAnswerResponse
│
└── use_cases/               # 15 个用例
    ├── ingest_document.py        # 导入文档
    ├── query_knowledge.py        # 检索知识
    ├── generate_answer.py        # 生成回答
    ├── delete_document.py        # 删除文档
    ├── list_documents.py         # 列出文档
    ├── get_document_detail.py    # 文档详情
    ├── get_document_summary.py   # 文档摘要
    ├── get_knowledge_status.py   # 知识库状态
    ├── rebuild_collection.py     # 重建索引
    ├── list_collections.py       # 列出集合
    ├── run_evaluation.py         # 运行评估
    ├── list_evaluation_reports.py
    ├── get_evaluation_report_detail.py
    ├── list_traces.py
    └── get_trace_detail.py
```

**Use Case 的标准模式**：

```python
class QueryKnowledgeUseCase:
    """一个典型的 Use Case"""

    def __init__(self, retrieval_service, trace_collector):
        # 1. 通过构造函数接收依赖（DI 注入）
        self.retrieval_service = retrieval_service
        self.trace_collector = trace_collector

    def execute(self, request: QueryRequest) -> QueryResponse:
        # 2. 接收请求 DTO，执行业务编排
        with self.trace_collector.start_trace("query") as trace:
            results = self.retrieval_service.search(request.query, request.top_k)
            trace.record("retrieval", {"count": len(results)})
        # 3. 返回响应 DTO
        return QueryResponse(results=results, trace_id=trace.trace_id)
```

**Use Case 不知道的事情**：
- 不知道数据存在 Weaviate 还是 ChromaDB
- 不知道 Embedding 是 Zhipu 还是本地 Hash
- 不知道用户通过 REST API 还是 MCP Tools 调用
- 不知道配置从哪里加载

### 3.3 Presentation 层（展示层）

**位置**：`api/` + `mcp/`

**职责**：接收外部请求，调用 Use Case，返回格式化结果。

两种展示方式共享同一套 Use Case：

```
同一个 Use Case ──────────────────────────────────────────────
                                                               │
    ┌──────────────────────────────────────────────────────────┤
    │                                                          │
    ▼                                                          ▼
REST API 路由                                          MCP 工具函数

@router.post("/query")                                 def knowledge_query(
def query_knowledge(request):                               query: str,
    response = get_container()                              top_k: int = 5,
        .query_use_case                                ) -> QueryResponse:
        .execute(request)                                  return get_container()
    return {                                                   .query_use_case
        "code": 0,                                             .execute(
        "data": response.model_dump()                              QueryRequest(
    }                                                                  query=query,
                                                                      top_k=top_k
                                                                  ))
```

### 3.4 Infrastructure 层（基础设施层 — 最外层）

**位置**：`infrastructure/`

**职责**：所有具体的技术实现。数据库、API 调用、文件 I/O、缓存。

```
infrastructure/
├── embedding/              # 向量生成
│   ├── zhipu_embedding.py  #   智谱 API（生产）
│   ├── hash_embedding.py   #   本地哈希（测试）
│   └── caching_embedding.py#   Redis 缓存装饰器
├── llm/                    # 大语言模型
│   ├── deepseek_llm.py     #   DeepSeek API（生产）
│   └── stub_llm.py         #   静态回复（测试）
├── vector_store/           # 向量数据库
│   ├── weaviate_store.py   #   Weaviate Embedded（生产）
│   ├── chroma_store.py     #   ChromaDB（备选）
│   └── memory_store.py     #   内存（测试）
├── sparse/                 # 稀疏检索
│   └── bm25_store.py       #   BM25 JSON 持久化
├── loaders/                # 文件加载
│   ├── compound_loader.py  #   按扩展名路由
│   ├── text_loader.py      #   .txt / .md
│   └── pdf_loader.py       #   .pdf
├── splitters/              # 文本分块
│   └── simple_splitter.py  #   滑动窗口 + 边界优化
├── rerank/                 # 重排序
│   └── lexical_reranker.py #   词元重叠
├── repositories/           # 数据持久化
│   ├── json_repositories.py       #   JSON 文件
│   ├── jsonl_trace_repository.py  #   JSONL 追踪
│   └── json_evaluation_repository.py
├── pipeline.py             # 导入管道编排
├── providers/              # 工厂方法
│   └── factories.py        #   按 provider 名创建实例
├── redis/                  # 缓存
│   ├── client.py           #   Redis 连接
│   └── cache.py            #   缓存服务
├── prompts/                # 提示词
│   ├── answer_prompt_builder.py
│   └── template_loader.py
├── ingestion/              # 导入前校验
│   ├── source_inspector.py
│   └── source_validator.py
└── evaluation/
    └── dataset_loader.py
```

### 3.5 Core 层（横切关注点）

**位置**：`core/`

**职责**：被所有层共享的基础设施。

```
core/
├── settings.py     # 配置加载（YAML + 环境变量 + Pydantic 校验）
├── container.py    # DI 容器（手动接线，唯一知道所有层的地方）
├── exceptions.py   # 异常体系（RagMcpError → 7 个子类）
└── tracing.py      # 结构化追踪（JSONL 持久化）
```

---

## 4. DI 容器 — 一切汇聚的地方

`core/container.py` 是整个项目的**组合根（Composition Root）**——唯一一个知道所有具体实现的文件。

```
┌───────────────────────────────────────────────────────────────────┐
│                    ApplicationContainer                            │
│                                                                   │
│  ┌─ Step 1: 创建基础设施对象 ──────────────────────────────────┐  │
│  │                                                              │  │
│  │  embedding_provider = create_embedding_provider(settings)    │  │
│  │      │  └─→ ZhipuEmbeddingProvider 或 HashEmbeddingProvider  │  │
│  │                                                              │  │
│  │  vector_store = _create_vector_store()                       │  │
│  │      │  └─→ WeaviateVectorStore / ChromaVectorStore / Memory │  │
│  │                                                              │  │
│  │  sparse_index = JsonBm25Store(...)                           │  │
│  │  reranker = create_reranker(settings)                        │  │
│  │  llm_provider = create_llm_provider(settings)                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                     │
│                              ▼                                     │
│  ┌─ Step 2: 创建领域服务 ──────────────────────────────────────┐  │
│  │                                                              │  │
│  │  retrieval_service = HybridRetrievalService(                 │  │
│  │      embedding_provider=embedding_provider,                  │  │
│  │      vector_store=vector_store,                              │  │
│  │      sparse_index=sparse_index,                              │  │
│  │      reranker=reranker,                                      │  │
│  │  )                                                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                     │
│                              ▼                                     │
│  ┌─ Step 3: 创建 Use Case ──────────────────────────────────────┐  │
│  │                                                              │  │
│  │  query_use_case = QueryKnowledgeUseCase(                     │  │
│  │      retrieval_service=retrieval_service,                    │  │
│  │      trace_collector=trace_collector,                        │  │
│  │  )                                                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

**为什么这样设计？**

Use Case 不知道自己用的是 Weaviate 还是 ChromaDB。它只知道自己有一个 `vector_store`，上面有 `upsert()`、`query()`、`delete_by_document()` 三个方法。Container 在启动时决定注入哪个实现。

这意味着：
- 配置改一行 `provider: "chroma"` → 整个应用切换到 ChromaDB，**代码零改动**
- 换一个新的 LLM → 写一个新的 Provider 类，注册到工厂，配置改一行，**代码零改动**

---

## 5. 依赖方向规则

```
Presentation
     │  只调用 Use Case
     ▼
Application (Use Cases + DTOs)
     │  只使用 Domain Entities 和 Core
     ▼
Domain (Entities + Contracts + Services)
     │  零外部依赖（纯 Python）
     ▼
Core (Settings + Exceptions + Tracing)

Infrastructure
     │  实现 Domain Contracts，使用 Core
     │  被容器注入到 Application / Domain
     ▼
（被 Container 拉进来，不主动依赖任何人）
```

**依赖方向铁律**：

| 层 | 可以导入 | 不可以导入 |
|---|---|---|
| Domain | 标准库 | application, infrastructure, core |
| Application | domain, core | infrastructure, api, mcp |
| Presentation | application, core | domain, infrastructure |
| Infrastructure | domain, core | application, api, mcp |
| Core | 自身 | domain, application, infrastructure |

**例外**：Container 是组合根，它导入一切——这是设计意图。

---

## 6. 可插拔的 Provider 体系

通过 **工厂模式 + 配置驱动**，每个外部依赖都可以热切换：

```python
# infrastructure/providers/factories.py

def create_embedding_provider(settings):
    provider = settings.embedding.provider
    if provider == "zhipu":
        return ZhipuEmbeddingProvider(...)    # 生产
    if provider == "hash":
        return HashEmbeddingProvider(...)     # 测试
    raise ConfigurationError(...)

def create_llm_provider(settings):
    provider = settings.llm.provider
    if provider == "deepseek":
        return DeepSeekLlmProvider(...)       # 生产
    if provider == "stub":
        return StubLlmProvider(...)           # 测试
    ...

def create_vector_store(settings):     # container.py 中
    provider = settings.vector_store.provider
    if provider == "weaviate":
        return WeaviateVectorStore(...)       # 生产
    if provider == "chroma":
        return ChromaVectorStore(...)         # 备选
    if provider == "memory":
        return InMemoryVectorStore(...)       # 测试
    ...
```

```yaml
# 切换 provider 只需改配置，代码零改动
embedding:
  provider: "zhipu"     # ← 改为 "hash" 即切换到测试模式

llm:
  provider: "deepseek"  # ← 改为 "stub" 即切换到测试模式

vector_store:
  provider: "weaviate"  # ← 改为 "chroma" 即切换回 ChromaDB
```

---

## 7. 请求处理流程

以 "用户查询知识库" 为例，追踪一个请求穿越所有层：

```
┌─── Presentation ──────────────────────────────────────────────────┐
│                                                                    │
│  REST: POST /api/v1/query {"query": "什么是 RAG", "top_k": 5}     │
│    │                                                               │
│    │  routes.py: query_knowledge(request)                          │
│    │    └─ get_container().query_use_case.execute(request)         │
│    │                                                               │
│  MCP: tools/call knowledge_query {"query": "什么是 RAG"}           │
│    │                                                               │
│    │  sdk_server.py: knowledge_query(query, top_k)                 │
│    │    └─ get_container().query_use_case.execute(                  │
│    │         QueryRequest(query=query, top_k=top_k))               │
│    │                                                               │
└────┼──────────────────────────────────────────────────────────────┘
     ▼
┌─── Application ───────────────────────────────────────────────────┐
│                                                                    │
│  QueryKnowledgeUseCase.execute(request)                            │
│    │                                                               │
│    ├─ 创建 TraceContext (core/tracing.py)                          │
│    ├─ 调用 retrieval_service.search(query, top_k)                  │
│    │       │                                                       │
│    │       ▼                                                       │
│    │  ┌─── Domain Service ──────────────────────────────────┐     │
│    │  │  HybridRetrievalService.search()                    │     │
│    │  │                                                      │     │
│    │  │  1. embed query → EmbeddingProvider (infrastructure) │     │
│    │  │  2. dense search → VectorStore (infrastructure)      │     │
│    │  │  3. sparse search → BM25 (infrastructure)            │     │
│    │  │  4. RRF fuse → 纯算法（domain 层内部）                 │     │
│    │  │  5. rerank → Reranker (infrastructure)               │     │
│    │  └──────────────────────────────────────────────────────┘     │
│    │                                                               │
│    ├─ 记录 trace                                                   │
│    └─ 构建 QueryResponse DTO 返回                                   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
     ▼
┌─── Infrastructure (被 Domain Service 调用) ────────────────────────┐
│                                                                    │
│  ZhipuEmbeddingProvider.embed_texts()  → HTTP POST Zhipu API      │
│  WeaviateVectorStore.query()            → Weaviate Embedded gRPC  │
│  JsonBm25Store.query()                  → JSON 文件 + BM25 算法    │
│  LexicalReranker.rerank()               → Token overlap 计算       │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 8. 异常体系

```
RagMcpError (基类)
  │
  ├── ConfigurationError    # 配置错误（缺少 API Key、文件不存在）
  ├── IngestionError        # 导入失败（文件格式不支持、读取失败）
  ├── SourceValidationError # 源文件校验失败（扩展名、大小、隐藏文件）
  ├── QueryError            # 查询错误
  ├── EvaluationError       # 评估错误
  ├── ProviderError         # 外部服务调用失败（Zhipu/DeepSeek/Weaviate）
  └── NotFoundError         # 资源不存在（文档/Trace/报告 ID 找不到）
```

每一层处理异常的方式不同：

| 层 | 行为 |
|---|---|
| Infrastructure | 抛出 `ProviderError` |
| Domain Service | 透传异常 |
| Application Use Case | 透传或转换为领域异常 |
| REST API | 捕获 → `HTTPException(400/404)` |
| MCP Tools | 捕获 → `ToolError` → `{"isError": true}` |

---

## 9. 架构优势总结

### 9.1 可测试性

```python
# 测试 Use Case 时，注入 mock 依赖
use_case = QueryKnowledgeUseCase(
    retrieval_service=MockRetrievalService(),  # 不需要真正的向量库
    trace_collector=MockTraceCollector(),       # 不需要真正的文件 I/O
)
result = use_case.execute(QueryRequest(query="test", top_k=3))
assert len(result.results) == 3
```

### 9.2 可替换性

```
换向量库:  写 WeaviateStore → 配置改一行 → 完成
换 LLM:    写 OpenAILlmProvider → 配置改一行 → 完成
换缓存:    写 MemcachedCache → 注册到工厂 → 完成
```

### 9.3 可扩展性

```
加新接口:  加 GraphQL Presentation → 复用所有 Use Case
加新功能:  加 Use Case → 注入到 Container → REST/MCP 各加一行
加新存储:  写 Infrastructure 实现 → 注册到 Container
```

---

## 10. 目录与文件速查表

| 层 | 目录 | 文件数 | 职责 |
|---|---|---|---|
| **Presentation** | `api/v1/`, `mcp/` | 4 | 接收请求、调用 Use Case、格式化响应 |
| **Application** | `application/use_cases/`, `application/dto/` | 17 | 业务编排、请求/响应定义 |
| **Domain** | `domain/entities/`, `domain/repositories/`, `domain/services/` | 5 | 数据模型、接口契约、核心算法 |
| **Core** | `core/` | 4 | 配置、DI 容器、异常、追踪 |
| **Infrastructure** | `infrastructure/` (14 子目录) | 30+ | 所有技术实现 |
| **Observability** | `observability/` | 5 | Streamlit Dashboard |
| **Entry** | 根目录 `main.py` | 1 | FastAPI 应用创建 |
