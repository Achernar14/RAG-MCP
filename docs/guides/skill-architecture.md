# Skill 架构详解 — 模块化能力组装系统

## 1. 为什么需要 Skill 架构

在 Skill 架构引入之前，`ApplicationContainer` 把所有 15 个 Use Case 全部硬编码在一处：

```
旧架构的问题:
──────────────

Container.__init__():
  self.ingest_use_case = ...
  self.query_use_case = ...
  self.generate_answer_use_case = ...
  self.delete_document_use_case = ...
  self.list_documents_use_case = ...
  ... (共 15 个)
  self.retrieval_service = ...
  self.pipeline = ...
  self.loader = ...
  self.splitter = ...
  ... (共 20+ 个依赖)

问题:
  ❌ 无法关闭某个能力（如不需要评估）
  ❌ 新增能力必须改动 Container
  ❌ 所有依赖一次性全部创建，无法按需加载
  ❌ 测试必须构造全部依赖
```

Skill 架构将这团硬编码拆成 **6 个独立的能力模块**，每个模块可以按需开关：

```
新架构:
───────

settings.yaml:
  skills:
    ingestion: true           ← 可独立开关
    retrieval: true
    generation: true
    document_management: true
    evaluation: false          ← 关闭评估，工具消失
    observability: true
```

---

## 2. 架构全景

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          ApplicationContainer                                │
│                                                                             │
│   Phase A: 共享基础设施（始终创建）                                          │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │  embedding_provider │ vector_store │ sparse_index │ reranker        │  │
│   │  llm_provider       │ redis_cache  │ trace_collector               │  │
│   │  document_repo      │ chunk_repo   │ trace_repo  │ eval_repo       │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   Phase B: Skill 按需组装（配置驱动）                                        │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                                                                      │  │
│   │   SkillRegistry                                                      │  │
│   │   ┌─────────────────────────────────────────────────────────────┐   │  │
│   │   │                                                             │   │  │
│   │   │  ┌──────────┐  ┌──────────┐  ┌──────────────┐             │   │  │
│   │   │  │ Ingestion│  │Document  │  │Observability │             │   │  │
│   │   │  │  Skill   │  │Mgmt     │  │  Skill       │             │   │  │
│   │   │  │  (4 tools)│  │(4 tools)│  │  (2 tools)   │             │   │  │
│   │   │  └────┬─────┘  └─────────┘  └──────────────┘             │   │  │
│   │   │       │ deps: none      deps: none    deps: none          │   │  │
│   │   │       │                                                    │   │  │
│   │   │       ▼                                                    │   │  │
│   │   │  ┌──────────┐                                             │   │  │
│   │   │  │Retrieval │                                             │   │  │
│   │   │  │  Skill   │                                             │   │  │
│   │   │  │  (1 tool)│                                             │   │  │
│   │   │  └──┬───┬───┘                                             │   │  │
│   │   │     │   │  deps: ["ingestion"]                            │   │  │
│   │   │     │   │                                                  │   │  │
│   │   │   ┌─┘   └──────────┐                                     │   │  │
│   │   │   ▼                 ▼                                      │   │  │
│   │   │  ┌──────────┐  ┌──────────┐                               │   │  │
│   │   │  │Generation│  │Evaluation│                               │   │  │
│   │   │  │  Skill   │  │  Skill   │                               │   │  │
│   │   │  │  (1 tool)│  │ (3 tools)│                               │   │  │
│   │   │  └──────────┘  └──────────┘                               │   │  │
│   │   │   deps: ["retrieval"]  deps: ["retrieval"]                │   │  │
│   │   │                                                             │   │  │
│   │   └─────────────────────────────────────────────────────────────┘   │  │
│   │                                                                      │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│   MCP Server ← skill_registry.get_enabled_tools() → 仅暴露已启用的工具     │
│   REST API   ← skill_registry.is_enabled() → 路由门控                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心类型

### 3.1 ToolDescriptor — 工具描述符

```python
@dataclass
class ToolDescriptor:
    name: str                    # MCP 工具名（如 "knowledge_query"）
    description: str             # LLM 看到的描述
    handler: Callable[..., Any]  # 实际执行的函数（闭包）
    return_type: type | None     # 结构化输出的类型注解
```

每个 Skill 注册若干个 `ToolDescriptor`，最终汇入 MCP Server 和 REST API。

### 3.2 SkillDescriptor — 技能描述符

```python
@dataclass
class SkillDescriptor:
    name: str                    # 唯一标识（如 "retrieval"）
    version: str                 # 版本号（如 "1.0.0"）
    description: str             # 人类可读描述
    enabled_by_default: bool     # 默认是否启用
    tools: list[ToolDescriptor]  # 承载的工具（注册时填充）
    dependencies: list[str]      # 依赖的其他 Skill
```

### 3.3 SkillModule — 技能协议（Protocol）

```python
class SkillModule(Protocol):
    """每个 Skill 必须实现的三个类方法"""

    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        """① 声明元数据：名称、版本、依赖"""
        ...

    @classmethod
    def register_tools(cls, container) -> list[ToolDescriptor]:
        """② 注册工具：创建闭包 handler，返回 ToolDescriptor 列表"""
        ...

    @classmethod
    def wire_container(cls, container, settings) -> None:
        """③ 接线：在 container 上创建 Use Case 和 Service 属性"""
        ...
```

使用 `Protocol` 而非 `ABC` — 不需要继承，只要实现这三个方法即可。

### 3.4 SkillRegistry — 技能注册中心

```python
class SkillRegistry:
    def register(module_cls)         # 注册一个 Skill 模块
    def enable(skill_name)           # 启用（根据配置）
    def disable(skill_name)          # 禁用
    def is_enabled(skill_name)       # 查询是否启用
    def get_enabled_tools(container) # 收集所有已启用 Skill 的工具
    def wire_all(container, settings)# 按拓扑序接线所有已启用 Skill
```

---

## 4. 六个 Skill 详解

### 4.1 依赖拓扑图

```
IngestionSkill ─────┐
DocumentMgmtSkill   │  无依赖（叶子节点）
ObservabilitySkill ──┘
         │
         │  RetrievalSkill 依赖 Ingestion
         │         │
         │         ├── GenerationSkill 依赖 Retrieval
         │         └── EvaluationSkill 依赖 Retrieval
         │
         ▼
  拓扑排序结果（Kahn 算法）:
  [ingestion, document_management, observability, retrieval, generation, evaluation]
```

**接线顺序保证**：`retrieval` 一定在 `ingestion` 之后、`generation` 之前。

### 4.2 各 Skill 明细

| Skill | 依赖 | 工具数 | 创建的 Container 属性 | 创建的 Use Case |
|---|---|---|---|---|
| `ingestion` | 无 | 4 | loader, splitter, pipeline, source_inspector, source_validator | IngestDocument, GetKnowledgeStatus, RebuildCollection, ListCollections |
| `retrieval` | ingestion | 1 | retrieval_service, dense_retrieval_service | QueryKnowledge |
| `generation` | retrieval | 1 | prompt_template_loader, answer_prompt_builder | GenerateAnswer |
| `document_management` | 无 | 4 | — | ListDocuments, GetDocumentDetail, GetDocumentSummary, DeleteDocument |
| `evaluation` | retrieval | 3 | — | RunEvaluation, ListEvaluationReports, GetEvaluationReportDetail |
| `observability` | 无 | 2 | — | ListTraces, GetTraceDetail |

**共计 15 个工具，与旧架构完全一致。**

### 4.3 工具分配表

| MCP 工具名 | 所属 Skill |
|---|---|
| `knowledge_ingest` | ingestion |
| `knowledge_status` | ingestion |
| `rebuild_collection` | ingestion |
| `list_collections` | ingestion |
| `knowledge_query` | retrieval |
| `generate_answer` | generation |
| `list_documents` | document_management |
| `get_document_detail` | document_management |
| `get_document_summary` | document_management |
| `delete_document` | document_management |
| `run_evaluation` | evaluation |
| `list_evaluation_reports` | evaluation |
| `get_evaluation_report` | evaluation |
| `list_traces` | observability |
| `get_trace_detail` | observability |

---

## 5. 启动流程

### 5.1 容器初始化两阶段

```python
class ApplicationContainer:
    def __init__(self, settings):
        # Phase A: 共享基础设施（无条件创建）
        self.vector_store = self._create_vector_store()
        self.sparse_index = JsonBm25Store(...)
        self.embedding_provider = ...
        self.llm_provider = ...
        # ... 其他共享依赖

        # Phase B: Skill 按需组装
        self._skill_registry = _create_skill_registry()  # 注册全部 6 个 Skill
        self._enable_skills_from_settings()               # 读取 YAML 开关
        self._skill_registry.wire_all(self, settings)     # 按拓扑序接线
```

### 5.2 详细时序

```
ApplicationContainer.__init__(settings)
  │
  ├── Phase A: 创建共享基础设施
  │     ├── vector_store (weaviate/chroma/memory)
  │     ├── sparse_index (BM25)
  │     ├── embedding_provider (zhipu/hash)
  │     ├── llm_provider (deepseek/stub)
  │     ├── reranker
  │     ├── trace_collector
  │     └── redis_cache (optional)
  │
  ├── Phase B: Skill 注册
  │     ├── _create_skill_registry()
  │     │     ├── registry.register(IngestionSkill)
  │     │     ├── registry.register(RetrievalSkill)
  │     │     ├── registry.register(GenerationSkill)
  │     │     ├── registry.register(DocumentManagementSkill)
  │     │     ├── registry.register(EvaluationSkill)
  │     │     └── registry.register(ObservabilitySkill)
  │     │
  │     ├── _enable_skills_from_settings()
  │     │     ├── settings.skills.ingestion == True  → enable("ingestion")
  │     │     ├── settings.skills.retrieval == True  → enable("retrieval")
  │     │     └── ... (读取 6 个开关)
  │     │
  │     └── registry.wire_all(self, settings)
  │           ├── 拓扑排序 → [ingestion, doc_mgmt, observability, retrieval, generation, evaluation]
  │           │
  │           ├── IngestionSkill.wire_container(container, settings)
  │           │     → container.loader, container.pipeline, container.ingest_use_case, ...
  │           │
  │           ├── DocumentManagementSkill.wire_container(container, settings)
  │           │     → container.list_documents_use_case, container.delete_document_use_case, ...
  │           │
  │           ├── ObservabilitySkill.wire_container(container, settings)
  │           │     → container.list_traces_use_case, ...
  │           │
  │           ├── RetrievalSkill.wire_container(container, settings)
  │           │     → container.retrieval_service, container.query_use_case
  │           │     （引用 container.embedding_provider 等 Phase A 创建的共享依赖）
  │           │
  │           ├── GenerationSkill.wire_container(container, settings)
  │           │     → container.generate_answer_use_case
  │           │     （引用 container.query_use_case，由 RetrievalSkill 创建）
  │           │
  │           └── EvaluationSkill.wire_container(container, settings)
  │                 → container.run_evaluation_use_case
  │                 （引用 container.query_use_case，由 RetrievalSkill 创建）
  │
  └── 初始化完成
```

---

## 6. MCP Server 如何消费 Skill

`sdk_server.py` 不再硬编码 15 个工具函数，而是从 `SkillRegistry` 动态收集：

```python
def _build_fastmcp_server() -> FastMCP:
    container = get_container()
    server = FastMCP(name=settings.mcp.server_name)

    # 从 SkillRegistry 获取所有已启用 Skill 的工具
    tools = container.skill_registry.get_enabled_tools(container)

    for desc in tools:
        # 修补 handler 的元数据（FastMCP 需要读取 __name__, __doc__）
        desc.handler.__name__ = desc.name
        desc.handler.__doc__ = desc.description
        if desc.return_type:
            desc.handler.__annotations__["return"] = desc.return_type

        server.add_tool(desc.handler, name=desc.name, structured_output=True)

    return server
```

**效果**：禁用一个 Skill → 其工具从 MCP 协议中消失 → LLM 看不到也调不了。

---

## 7. REST API 如何消费 Skill

`routes.py` 使用 `_require_skill()` 门控每个路由：

```python
def _require_skill(name: str) -> None:
    if not get_container().skill_registry.is_enabled(name):
        raise HTTPException(status_code=404, detail=f"Skill '{name}' is not enabled")

@router.post("/query")
def query_knowledge(request):
    _require_skill("retrieval")    # ← 门控
    return get_container().query_use_case.execute(request)

@router.post("/answers/generate")
def generate_answer(request):
    _require_skill("generation")   # ← 门控
    return get_container().generate_answer_use_case.execute(request)
```

**效果**：禁用一个 Skill → 其路由返回 HTTP 404 → 客户端知道该能力不可用。

### 路由与 Skill 的映射

| 路由 | Skill 门控 |
|---|---|
| `POST /ingest` | `ingestion` |
| `GET /stats` | `ingestion` |
| `POST /collections/rebuild` | `ingestion` |
| `GET /collections` | `ingestion` |
| `POST /query` | `retrieval` |
| `POST /answers/generate` | `generation` |
| `GET /documents` | `document_management` |
| `GET /documents/{id}` | `document_management` |
| `GET /documents/{id}/detail` | `document_management` |
| `DELETE /documents/{id}` | `document_management` |
| `POST /evaluations/run` | `evaluation` |
| `GET /evaluations` | `evaluation` |
| `GET /evaluations/{id}` | `evaluation` |
| `GET /traces` | `observability` |
| `GET /traces/{id}` | `observability` |
| `GET /health` | **无门控**（始终可用） |

---

## 8. 配置方式

### 8.1 全部启用（默认）

```yaml
# config/settings.yaml
skills:
  ingestion: true
  retrieval: true
  generation: true
  document_management: true
  evaluation: true
  observability: true
```

### 8.2 仅检索模式

```yaml
skills:
  ingestion: true
  retrieval: true
  generation: false          # 不需要 LLM 生成回答
  document_management: true
  evaluation: false           # 不需要评估
  observability: false        # 不需要追踪
```

效果：MCP 只暴露 9 个工具（ingestion 4 + retrieval 1 + doc_mgmt 4），`generate_answer`、评估、追踪相关工具消失。

### 8.3 纯导入模式

```yaml
skills:
  ingestion: true
  retrieval: false            # 不需要检索
  generation: false           # 不需要回答生成
  document_management: true   # 需要查看文档列表
  evaluation: false
  observability: false
```

效果：仅文档导入 + 文档管理可用。适合批量导入场景。

### 8.4 依赖规则

禁用一个 Skill 会级联影响依赖它的 Skill：

```
禁用 ingestion:
  → retrieval 无法接线（依赖 ingestion 创建的 pipeline）
  → generation 无法接线（依赖 retrieval 的 query_use_case）
  → evaluation 无法接线（依赖 retrieval 的 query_use_case）

禁用 retrieval:
  → generation 无法接线
  → evaluation 无法接线
```

> **当前不会自动级联禁用。** 如果你禁用了 `ingestion` 但保留 `retrieval: true`，启动时会因为 `container.pipeline` 不存在而报错。配置时需注意依赖关系。

---

## 9. 工具 Handler 的闭包模式

每个 Skill 通过闭包捕获 Container 引用，避免硬编码全局状态：

```python
class IngestionSkill:
    @staticmethod
    def _knowledge_ingest(container):
        """返回一个闭包，捕获 container 引用"""

        def knowledge_ingest(path: str, force_rebuild: bool = False):
            return container.ingest_use_case.execute(
                IngestRequest(path=path, force_rebuild=force_rebuild)
            )

        return knowledge_ingest
```

```
调用链:
  MCP tools/call "knowledge_ingest" {"path": "doc.pdf"}
    │
    ▼
  FastMCP 找到 handler 闭包
    │
    ▼
  knowledge_ingest(path="doc.pdf", force_rebuild=False)
    │  ← 闭包捕获了 container 引用
    ▼
  container.ingest_use_case.execute(IngestRequest(...))
    │  ← Use Case 由 IngestionSkill.wire_container() 创建
    ▼
  业务逻辑执行
```

---

## 10. Skill 文件结构

```
backend/src/rag_mcp/
├── core/
│   ├── skill_registry.py         # SkillRegistry + SkillModule Protocol
│   ├── container.py              # Phase A (共享) + Phase B (Skill 接线)
│   └── settings.py               # SkillSettings (6 个 bool 开关)
│
└── skills/                        # 每个 Skill 一个子目录
    ├── __init__.py                # 包标记
    ├── ingestion/
    │   └── __init__.py            # IngestionSkill (4 tools)
    ├── retrieval/
    │   └── __init__.py            # RetrievalSkill (1 tool)
    ├── generation/
    │   └── __init__.py            # GenerationSkill (1 tool)
    ├── document_management/
    │   └── __init__.py            # DocumentManagementSkill (4 tools)
    ├── evaluation/
    │   └── __init__.py            # EvaluationSkill (3 tools)
    └── observability/
        └── __init__.py            # ObservabilitySkill (2 tools)
```

---

## 11. 如何新增一个 Skill

### Step 1：创建 Skill 目录

```bash
mkdir -p backend/src/rag_mcp/skills/my_skill
```

### Step 2：实现 SkillModule 协议

```python
# skills/my_skill/__init__.py
from rag_mcp.core.skill_registry import SkillDescriptor, ToolDescriptor

class MySkill:
    @classmethod
    def descriptor(cls) -> SkillDescriptor:
        return SkillDescriptor(
            name="my_skill",
            version="1.0.0",
            description="我的自定义能力",
            dependencies=["retrieval"],   # 如果依赖其他 Skill
        )

    @classmethod
    def register_tools(cls, container) -> list[ToolDescriptor]:
        return [
            ToolDescriptor(
                name="my_tool",
                description="做某件事",
                handler=cls._my_tool(container),
                return_type=MyResponse,
            ),
        ]

    @classmethod
    def wire_container(cls, container, settings) -> None:
        from rag_mcp.application.use_cases.my_use_case import MyUseCase
        container.my_use_case = MyUseCase(
            dependency=container.some_shared_dep,  # Phase A 创建的
        )

    @staticmethod
    def _my_tool(container):
        def my_tool(param: str):
            return container.my_use_case.execute(MyRequest(param=param))
        return my_tool
```

### Step 3：注册到 SkillRegistry

在 `core/container.py` 的 `_create_skill_registry()` 中添加：

```python
from rag_mcp.skills.my_skill import MySkill
registry.register(MySkill)
```

### Step 4：添加配置开关

在 `core/settings.py` 的 `SkillSettings` 中添加：

```python
class SkillSettings(BaseModel):
    # ...existing
    my_skill: bool = True
```

在 `config/settings.yaml` 中添加：

```yaml
skills:
  # ...existing
  my_skill: true
```

### Step 5：添加 REST 路由（可选）

在 `api/v1/routes.py` 中添加带 Skill 门控的路由：

```python
@router.post("/my-endpoint")
def my_endpoint(request):
    _require_skill("my_skill")
    return get_container().my_use_case.execute(request)
```

**完成。** 无需修改 MCP Server、Container 核心逻辑或其他 Skill。

---

## 12. 旧架构 vs 新架构对比

```
┌──────────────────────┬─────────────────────────┬─────────────────────────┐
│                      │  旧架构                  │  Skill 架构              │
├──────────────────────┼─────────────────────────┼─────────────────────────┤
│ Use Case 定义位置    │  container.py 硬编码     │  各 Skill 的 wire方法    │
│ MCP 工具定义位置     │  sdk_server.py 硬编码    │  各 Skill 的闭包 handler │
│ REST 路由门控       │  无（全部可用）           │  _require_skill() 门控   │
│ 关闭某个能力         │  不支持                  │  YAML 改一行             │
│ 新增能力             │  改 container + sdk      │  加一个 Skill 目录       │
│ 跨 Skill 依赖       │  隐式（执行顺序靠代码）   │  显式声明 + 拓扑排序     │
│ 测试隔离             │  需 mock 全部依赖        │  只启用目标 Skill        │
│ 代码组织             │  1 个巨大 Container      │  6 个独立 Skill 模块     │
└──────────────────────┴─────────────────────────┴─────────────────────────┘
```
