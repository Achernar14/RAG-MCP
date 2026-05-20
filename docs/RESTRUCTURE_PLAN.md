# 项目重构与结构规划

> 目标：在保留当前项目核心功能（RAG + MCP Server + Dashboard + Ingestion + Embedding）的前提下，重构为更清晰、模块化、可测试且易维护的 Python Web 项目结构。

## 1. 项目定位与核心功能

- 本地化的 RAG（Retrieval-Augmented Generation）服务，提供文档摄取（ingestion）、切分、向量化（embedding）、向量存储与检索（Chroma）、重排序（reranker）和质量评估。
- 作为一个 MCP（Model Context Protocol）Server，暴露标准的工具（tools）接口供 MCP Client（如 Copilot/Claude 等）通过 JSON-RPC 或 stdio/HTTP 调用。
- 提供观测与可视化 Dashboard（基于 Streamlit），用于健康检查、索引状态查看与简单交互。

## 2. 当前痛点（简要）

- 项目目录与模块职责混淆，部分功能实现分散且命名不一致。
- embedding provider 未统一抽象，provider 的注册/发现机制不完全。
- `main.py` 仅做配置校验，不具备长期运行的 MCP 服务入口；`mcp_server` 的可运行入口实现不集中。
- 配置文件包含敏感信息并直接在仓库中存在历史记录风险。

## 3. 设计原则

- 单一职责：每个包/模块只负责一件事。
- 明确边界：通过接口（抽象基类/协议）定义 provider/存储/工具的契约。
- 可插拔：新增 provider/向量库时仅需实现接口并在注册表中登记。
- 易测试：单元与集成测试覆盖关键路径（ingestion→embedding→store→mcp-tool）。
- 安全：默认不在 repo 中保存密钥，使用 `config/settings.yaml.example` 与环境变量。

## 4. 建议的新项目结构（树状）

```
README.md
pyproject.toml
pyproject.lock (可选)
LICENSE
config/
  settings.yaml.example
  prompts/
src/
  app.py                  # 可选：统一启动入口（CLI wrapper）
  core/
    __init__.py
    settings.py           # 配置加载与校验（从 env 覆盖）
    types.py              # Domain types: Document, Chunk, RetrievalResult
    registry.py           # provider / tool 注册表
  mcp_server/
    __init__.py
    server.py             # MCP Server 入口（stdio/http transport）
    protocol_handler.py   # JSON-RPC 请求路由与工具分发
    tools/
      __init__.py
      query_tool.py
      ingest_tool.py
  ingestion/
    __init__.py
    pipeline.py           # 摄取流水线（loader -> splitter -> embeddor -> store）
    document_manager.py
    chunking/
      chunker.py
      heuristics.py
    loader/
      pdf_loader.py
      text_loader.py
  libs/
    __init__.py
    embedding/
      base.py              # Embedding 接口/抽象
      openai.py
      zhipu.py
      factory.py           # 根据配置创建 provider 实例
    vector_store/
      base.py
      chroma_store.py
      factory.py
    reranker/
      cross_encoder.py
  observability/
    __init__.py
    logger.py
    dashboard/
      app.py               # Streamlit app
  api/
    http_server.py        # 可选：对外轻量 HTTP API (Flask/FastAPI)
scripts/
  start_dashboard.py
  ingest.py
  query.py
tests/
  unit/
  integration/
  e2e/
docs/
  RESTRUCTURE_PLAN.md
data/
  db/
    chroma/
logs/

```

## 5. 模块职责与边界（逐项说明）

- `src/core/settings.py`
  - 责任：加载 `config/settings.yaml` 并允许环境变量覆盖敏感项（例如 `ZHIPU_API_KEY`）。提供类型化的配置对象。

- `src/core/types.py`
  - 责任：全项目共享的 Domain 类型，例如 `Document`, `Chunk`, `EmbeddingRecord`, `RetrievalResult`。便于序列化、测试与接口兼容。

- `src/core/registry.py`
  - 责任：运行时注册/发现 provider（embedding, vector_store, reranker）。支持通过 entrypoints 或配置动态加载实现。

- `src/libs/embedding/`（provider 实现）
  - `base.py`：定义 `EmbeddingProvider` 抽象，包括 `embed(texts: List[str]) -> List[List[float]]`。
  - `factory.py`：根据 `settings.embedding.provider` 创建 provider 实例并注入配置（base_url、api_key）。
  - 各 provider 文件实现细节（`zhipu.py`、`openai.py`）并包含单元测试 mock。

- `src/ingestion/`（摄取流水线）
  - 责任：把文件/目录摄取为 `Document`，执行 chunking、元数据提取，并送入 embedding + vector_store。设计为可重试、可观察的流水线。

- `src/libs/vector_store/`
  - `base.py`：定义 `VectorStore` 接口（upsert, query, delete, persist）。
  - `chroma_store.py`：Chroma 的封装实现（并负责本地 path 管理 `data/db/chroma`）。

- `src/mcp_server/`
  - 责任：实现 MCP 协议的 transport 层（stdio 或 HTTP），接收工具调用，调用 registry 中的工具实现并返回 MCP 格式的响应。

- `src/observability/dashboard/app.py`
  - 责任：提供索引健康、最近查询、缓存命中率、简单手动查询面板。

## 6. 接口示例（Embedding Provider）

```python
# src/libs/embedding/base.py
from typing import List, Protocol

class EmbeddingProvider(Protocol):
    def embed(self, texts: List[str]) -> List[List[float]]:
        """将文本列表转换为嵌入向量列表"""
```

`factory.py` 将返回符合该协议的实例；上层只依赖接口，不关心实现。

## 7. 迁移/重构步骤（渐进式）

1. 新增 `src/core/types.py` 和 `src/core/registry.py`（为后续改动建立契约）。
2. 在 `src/libs/embedding/` 创建 `base.py` 与 `factory.py`，并迁移现有 provider 代码到该目录（先以 wrapper 形式保留原实现）。
3. 将 `ingestion/` 的功能模块化（loader, chunker, pipeline），逐个迁移并覆盖接口，添加单元测试。
4. 实现 `src/libs/vector_store/chroma_store.py` 的 `VectorStore` 接口实现并更新现有调用点。
5. 在 `mcp_server/` 中实现或修复 `server.py` 的可运行入口（Stdio transport），并编写一个最小 MCP 工具 `query_tool` 用于端到端 smoke test。
6. 更新 `scripts/`，提供 `scripts/start_services.sh` 或 `start_services.ps1` 来同时启动 Dashboard 与 MCP Server（可选使用 `tmux` 或 Windows 的后台进程）。
7. 把敏感配置移到环境变量：更新 `settings.py` 读取逻辑并把 `config/settings.yaml` 中的密钥设为空，写入 `config/settings.yaml.example`。
8. 添加 CI：`pytest`、lint（flake8/ruff）、type check（mypy）。

## 8. 测试策略

- 单元测试：每个 provider、vector store、chunker 单独覆盖。
- 集成测试：使用内存/本地 Chroma 实例做摄取-检索一条流程测试。
- E2E：启动 MCP Server（测试模式）并用 `tests/e2e/test_mcp_client.py` 模拟客户端请求，验证响应格式与文本质量。

## 9. 开发者体验（建议）

- 提供 `Makefile` 或 `scripts/dev_setup.ps1` 来：创建/激活 venv、安装依赖、运行单元测试、启动 dashboard 与 mcp server。
- 编写 `CONTRIBUTING.md` 与 `CODE_STYLE.md`。

## 10. 安全与运维建议

- 不在仓库保留密钥历史；若密钥曾泄露，重新生成并撤销旧密钥。
- 使用 `.env` 与 `python-dotenv`（仅在开发）、或系统环境变量与 secrets 管理（生产）。
- 为 `data/db/chroma` 提供定期备份策略与清理脚本。

## 11. 路线图与优先级（3个月建议）

- Week 1-2：建立 `core` 抽象、provider factory；把 `zhipu` 封装为 provider。
- Week 3-4：模块化 `ingestion`、`vector_store` 并通过 CI 保证核心测试通过。
- Month 2：实现可运行的 MCP Server，完成 E2E smoke tests。
- Month 3：强化 Dashboard、文档、完善 CI、代码风格与示例数据。

---

如需，我可以接着：
- 直接在 `src/libs/embedding/` scaffold `base.py` 与 `zhipu.py` 的初始实现并添加单元测试；或
- 把 `config/settings.yaml` 中密钥替换为环境变量引用并更新 `settings.py` 的读取逻辑。

已把此文档保存为 `docs/RESTRUCTURE_PLAN.md`。请告诉我接下来要优先执行的重构步骤。