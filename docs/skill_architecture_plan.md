# RAG-MCP Skill 化架构规划

## Context

RAG-MCP 项目当前有 15 个 MCP 工具和 14 个 Use Case，全部在 `sdk_server.py` 的扁平列表和 `container.py` 的单体构造器中注册。随着功能增长（roadmap 中的多模态、高级评测、Vision Provider 等），需要将能力按"技能"维度组织为可插拔模块，同时识别值得接入的外部 MCP 工具。

本文档仅规划，不执行。

---

## 一、内部技能划分（6 个 Skill）

将现有 15 个 MCP 工具 / 14 个 Use Case 归纳为 6 个内部 Skill 模块。每个 Skill 拥有独立的工具集、Use Case 和配置开关。

### 1.1 技能依赖图

```
ingestion (基础，无依赖)
    │
    ▼
retrieval (依赖: 共享 embedding + vector 基础设施)
    │
    ├──────────┐
    ▼          ▼
generation  evaluation
(依赖       (依赖: retrieval)
 retrieval)

document_management (依赖: 共享 repositories)
observability       (依赖: trace 基础设施，消费所有 skill)
```

### 1.2 Skill: `ingestion`（摄取技能）

| 维度 | 内容 |
|------|------|
| **职责** | 文档加载、校验、切分、向量化、索引、集合管理 |
| **MCP 工具** | `knowledge_ingest`, `knowledge_status`, `rebuild_collection`, `list_collections` |
| **Use Cases** | `IngestDocumentUseCase`, `GetKnowledgeStatusUseCase`, `RebuildCollectionUseCase`, `ListCollectionsUseCase` |
| **专属基础设施** | `IngestionPipeline`, `LocalSourceInspector`, `LocalSourceValidator`, `CompoundDocumentLoader`, `TextDocumentLoader`, `PdfDocumentLoader`, `SimpleTextSplitter`, `file_metadata.py` |
| **共享依赖** | `EmbeddingProvider`, `VectorStoreRepository`, `SparseIndexRepository`, `DocumentRepository`, `ChunkRepository` |
| **配置节** | `ingestion`, `embedding`, `embedding_provider` |
| **开关** | `skills.ingest: true` |

### 1.3 Skill: `retrieval`（检索技能）

| 维度 | 内容 |
|------|------|
| **职责** | 混合 Dense + Sparse 检索、RRF 融合、Rerank |
| **MCP 工具** | `knowledge_query` |
| **Use Cases** | `QueryKnowledgeUseCase` |
| **专属服务** | `HybridRetrievalService`, `RetrievalService` |
| **共享依赖** | `EmbeddingProvider`, `VectorStoreRepository`, `SparseIndexRepository`, `BaseReranker` |
| **配置节** | `retrieval`, `rerank` |
| **开关** | `skills.retrieval: true` |

### 1.4 Skill: `generation`（生成技能）

| 维度 | 内容 |
|------|------|
| **职责** | LLM 接地的答案生成与引用 |
| **MCP 工具** | `generate_answer` |
| **Use Cases** | `GenerateAnswerUseCase` |
| **专属基础设施** | `AnswerPromptBuilder`, `FilePromptTemplateLoader`, `config/prompts/*` |
| **共享依赖** | `LlmProvider`，**组合 retrieval skill 的 `QueryKnowledgeUseCase`** |
| **配置节** | `llm`, `prompts` |
| **开关** | `skills.generation: true` |

### 1.5 Skill: `document_management`（文档管理技能）

| 维度 | 内容 |
|------|------|
| **职责** | 文档列表、详情、摘要、删除 |
| **MCP 工具** | `list_documents`, `get_document_detail`, `get_document_summary`, `delete_document` |
| **Use Cases** | `ListDocumentsUseCase`, `GetDocumentDetailUseCase`, `GetDocumentSummaryUseCase`, `DeleteDocumentUseCase` |
| **共享依赖** | `DocumentRepository`, `ChunkRepository`, `VectorStoreRepository`, `SparseIndexRepository` |
| **开关** | `skills.document_management: true` |

### 1.6 Skill: `evaluation`（评测技能）

| 维度 | 内容 |
|------|------|
| **职责** | 检索评测、报告持久化、评测结果浏览 |
| **MCP 工具** | `run_evaluation`, `list_evaluation_reports`, `get_evaluation_report` |
| **Use Cases** | `RunEvaluationUseCase`, `ListEvaluationReportsUseCase`, `GetEvaluationReportDetailUseCase` |
| **专属基础设施** | `load_evaluation_cases()`, `JsonlEvaluationReportRepository` |
| **共享依赖** | **组合 retrieval skill 的 `QueryKnowledgeUseCase`** |
| **配置节** | `evaluation` |
| **开关** | `skills.evaluation: true` |

### 1.7 Skill: `observability`（可观测技能）

| 维度 | 内容 |
|------|------|
| **职责** | Trace 收集、浏览、Dashboard |
| **MCP 工具** | `list_traces`, `get_trace_detail` |
| **Use Cases** | `ListTracesUseCase`, `GetTraceDetailUseCase` |
| **专属基础设施** | `JsonlTraceCollector`, `JsonlTraceRepository`, `DashboardService`, Dashboard 页面 |
| **配置节** | `observability` |
| **开关** | `skills.observability: true` |
| **注意** | 横切技能，消费所有其他 skill 的 trace 数据 |

### 1.8 共享内核（不属于任何 Skill）

| 组件 | 位置 |
|------|------|
| Settings 模型 | `core/settings.py` |
| DI 容器 | `core/container.py` |
| 异常层级 | `core/exceptions.py` |
| Provider 工厂 | `infrastructure/providers/factories.py` |
| 全部 Repository 实现 | `infrastructure/repositories/` |
| 全部 Provider 实现 | `infrastructure/embedding/`, `llm/`, `vector_store/`, `sparse/`, `rerank/` |
| Redis 缓存 | `infrastructure/redis/` |
| 领域实体 | `domain/entities/models.py` |
| 领域抽象 | `domain/repositories/contracts.py` |
| DTO 模型 | `application/dto/models.py` |
| FastAPI 路由 | `api/v1/routes.py` |
| MCP 协议层 | `mcp/protocol.py` |

---

## 二、外部技能接入（MCP 集成）

以下为值得接入的外部 MCP Server，由 MCP Client（Claude Desktop / Cursor 等）与 RAG-MCP 组合使用。

### 2.1 Web Search（网页搜索）

| 维度 | 内容 |
|------|------|
| **推荐 Server** | `tavily-mcp` 或 `@anthropic/brave-search-mcp` |
| **价值** | 本地知识库无法覆盖时，补充实时网络内容 |
| **与内部 Skill 协作** | `knowledge_query` 低置信度时 → 客户端 fallback 到 `web_search` → 结果可通过 `knowledge_ingest` 入库 |
| **RAG-MCP 侧配置** | 新增 `external.web_search` 配置节（provider, api_key_env, max_results） |
| **优先级** | P0 |

### 2.2 Filesystem（文件系统浏览）

| 维度 | 内容 |
|------|------|
| **推荐 Server** | `@anthropic/filesystem-mcp`（官方） |
| **价值** | 浏览本地目录发现待摄取文档，无需用户手动输入路径 |
| **与内部 Skill 协作** | 浏览目录 → 发现文件 → 调用 `knowledge_ingest` |
| **RAG-MCP 侧配置** | 路径白名单（客户端侧配置） |
| **优先级** | P1 |

### 2.3 Memory / Knowledge Graph（知识图谱）

| 维度 | 内容 |
|------|------|
| **推荐 Server** | `@modelcontextprotocol/server-memory` |
| **价值** | 跨会话记忆、实体关系追踪、用户偏好存储 |
| **与内部 Skill 协作** | 存储用户检索偏好 → 实体关系从摄取文档中提取 → "记住上次问过什么" |
| **RAG-MCP 侧配置** | 无需（客户端侧配置） |
| **优先级** | P1 |

### 2.4 Sequential Thinking（结构化推理）

| 维度 | 内容 |
|------|------|
| **推荐 Server** | `@anthropic/sequential-thinking-mcp` |
| **价值** | 引导 LLM 进行系统性评测、诊断、多步推理 |
| **与内部 Skill 协作** | 运行评测 → 分析失败 → 调整参数 → 重跑评测 的结构化工作流 |
| **RAG-MCP 侧配置** | 无需 |
| **优先级** | P2 |

### 2.5 Translation（翻译）

| 维度 | 内容 |
|------|------|
| **实现方式** | 复用内部 LLM Provider 或外部翻译 MCP |
| **价值** | 多语言 RAG：跨语言查询、翻译答案 |
| **与内部 Skill 协作** | 翻译查询 → `knowledge_query` → 翻译 `generate_answer` 输出 |
| **RAG-MCP 侧配置** | 新增 `external.translation` 配置节 |
| **优先级** | P2 |

### 2.6 Summarization（摘要）

| 维度 | 内容 |
|------|------|
| **实现方式** | 复用内部 LLM Provider，新增一个 Use Case |
| **价值** | 摄取前摘要、增强 `get_document_summary`、长答案压缩 |
| **与内部 Skill 协作** | 文档摄取前预摘要 → 提升切分质量 → 增强 document summary |
| **RAG-MCP 侧配置** | 复用 `llm` 配置 |
| **优先级** | P1 |

### 2.7 Code Analysis（代码分析）

| 维度 | 内容 |
|------|------|
| **推荐 Server** | 语言服务协议 MCP 或 `@anthropic/code-analysis-mcp` |
| **价值** | 代码仓库作为知识库，支持代码理解场景 |
| **与内部 Skill 协作** | 代码文件通过 `knowledge_ingest` 入库（text loader 已支持 `.py`/`.js` 等） |
| **RAG-MCP 侧配置** | 扩展 `ingestion.supported_extensions` |
| **优先级** | P2 |

---

## 三、Skill Registry 设计

### 3.1 核心接口

```
backend/src/rag_mcp/
├── core/
│   └── skill_registry.py     # NEW: SkillModule Protocol + SkillRegistry
└── skills/
    ├── __init__.py            # NEW: create_skill_registry() 工厂
    ├── ingestion/             # NEW: IngestionSkill
    │   └── __init__.py
    ├── retrieval/             # NEW: RetrievalSkill
    │   └── __init__.py
    ├── generation/            # NEW: GenerationSkill
    │   └── __init__.py
    ├── document_management/   # NEW: DocumentManagementSkill
    │   └── __init__.py
    ├── evaluation/            # NEW: EvaluationSkill
    │   └── __init__.py
    └── observability/         # NEW: ObservabilitySkill
        └── __init__.py
```

**原则：** Skill 模块是薄编排层，不包含业务逻辑、基础设施或领域模型。现有 `application/`、`domain/`、`infrastructure/` 代码全部保持原位不动。

### 3.2 每个 Skill 模块的职责

```python
class SkillModule(Protocol):
    @classmethod
    def descriptor(cls) -> SkillDescriptor: ...       # 声明元数据
    @classmethod
    def register_tools(cls, container) -> list: ...   # 返回 MCP 工具列表
    @classmethod
    def wire_container(cls, container, settings): ... # 向容器注册依赖
```

### 3.3 配置扩展

在 `core/settings.py` 新增：

```python
class SkillSettings(BaseModel):
    ingestion: bool = True
    retrieval: bool = True
    generation: bool = True
    document_management: bool = True
    evaluation: bool = True
    observability: bool = True

class Settings(BaseModel):
    # ... 现有 16 个子模型不变 ...
    skills: SkillSettings = Field(default_factory=SkillSettings)
```

### 3.4 容器重构策略

当前 `ApplicationContainer.__init__`（~200 行）一次性构造所有依赖。重构为：

| 阶段 | 内容 |
|------|------|
| **A. 共享基础设施** | 始终装配：settings, trace, providers, repositories, Redis |
| **B. 按 Skill 装配** | 每个 Skill 的 `wire_container()` 添加自己的 Use Case |
| **C. 按 Skill 注册工具** | `sdk_server.py` 从 `SkillRegistry.get_enabled_tools()` 构建工具列表 |

### 3.5 关键修改文件

| 文件 | 变更类型 |
|------|----------|
| `core/skill_registry.py` | 新建 |
| `core/settings.py` | 新增 `SkillSettings` |
| `core/container.py` | 重构为委托式装配 |
| `mcp/sdk_server.py` | 从 flat list → SkillRegistry 驱动 |
| `api/v1/routes.py` | 按启用 Skill 条件注册路由 |
| `skills/*.py` | 新建 6 个 Skill 模块 |

---

## 四、实施优先级

| 阶段 | 内容 | 周期 |
|------|------|------|
| **Phase 1** | 创建 `skill_registry.py` + `skills/` 骨架 + `SkillSettings`；以 `ingestion` 作为参考实现 | Week 1-2 |
| **Phase 2** | 迁移 `retrieval`、`generation`、`document_management` Skill | Week 3 |
| **Phase 3** | 迁移 `evaluation`、`observability` Skill；重构 `sdk_server.py` 和 `routes.py` | Week 4 |
| **Phase 4** | 补全测试、更新文档、验证 enable/disable 行为 | Week 5 |
| **Phase 5** | 编写外部 MCP 集成指南（Web Search、Filesystem 等） | Week 6+ |

---

## 五、验证方案

1. **回归测试** — 现有 82 个测试全部通过（测试目标是 Use Case，不依赖 Skill 层）
2. **开关测试** — 禁用任意 Skill 后，其 MCP 工具消失、REST 路由不可达、依赖 Skill 正确报错
3. **依赖测试** — 禁用 `retrieval` 时，`generation` 和 `evaluation` 工具不可用
4. **集成测试** — 全部 Skill 启用时，MCP Client 可发现并调用全部 15 个工具
