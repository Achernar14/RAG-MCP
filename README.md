# RAG-MCP

本项目是一个面向本地知识库场景的 RAG 后端与 MCP Server，当前仓库聚焦三类能力：

- 文档摄取：支持 `txt`、`md`、`pdf` 的加载、切分、索引与持久化
- 检索与问答：提供查询、答案生成、重建索引、评测等后端能力
- 可观测性：提供 Dashboard、trace、评测报告等本地调试入口

当前主代码位于 `backend/src/rag_mcp`，其余目录主要承载配置、样例数据、文档和测试。

## 项目结构

```text
RAG-MCP/
├── backend/                     # Python package 与后端实现
│   ├── pyproject.toml
│   └── src/rag_mcp/
├── config/                      # 配置模板与提示词
├── data/                        # 示例文档、评测集、本地运行数据目录
├── docs/                        # 设计与技术文档
├── scripts/                     # 本地启动脚本
└── tests/                       # 单元测试与集成测试
```

## 主要能力

- FastAPI API：提供摄取、查询、答案生成、文档管理、trace 查看、评测运行等接口
- MCP stdio server：通过官方 MCP SDK 暴露工具能力
- Streamlit Dashboard：查看知识库状态、trace、评测结果和运行概况
- 本地向量存储：默认使用 Chroma 持久化向量索引
- 混合检索：包含 dense、sparse、rerank 相关配置和服务装配

## 环境要求

- Python `3.11+`
- 建议使用虚拟环境
- Windows PowerShell、macOS/Linux shell 均可运行

## 安装

本项目使用 `backend/pyproject.toml` 作为依赖入口。

仅安装后端运行依赖：

```bash
pip install -e ./backend
```

安装开发依赖，包括 `pytest` 和 `streamlit`：

```bash
pip install -e ./backend[dev]
```

如果你使用 PowerShell 并且已经创建虚拟环境，典型流程如下：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .\backend[dev]
```

## 配置

项目默认从本地配置文件读取运行参数。初始化时建议先从模板复制：

```powershell
Copy-Item .\config\settings.yaml.example .\config\settings.yaml
Copy-Item .\.env.example .\.env
```

当前配置模板覆盖了这些核心项：

- `embedding` / `embedding_provider`
- `llm`
- `vector_store`
- `ingestion`
- `retrieval`
- `rerank`
- `observability`
- `evaluation`
- `prompts`
- `api`

默认模板里已经给出了本地开发可用的路径约定，例如：

- 向量库路径：`data/vector_store/chroma_live`
- trace 路径：`data/traces/traces.jsonl`
- 评测报告路径：`data/evaluations/reports.jsonl`

注意：

- `config/settings.yaml` 属于本地运行配置，默认不提交到仓库
- `.env` 用于保存密钥和环境变量，默认不提交到仓库

## 启动方式

这个仓库有三个常用入口：API、Dashboard、MCP Server。它们的用途不同，不建议混用。

### 1. 启动 FastAPI 服务

适合手动调试接口，或通过浏览器查看 Swagger 文档。

```bash
PYTHONPATH=backend/src uvicorn rag_mcp.main:app --reload
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='backend/src'
uvicorn rag_mcp.main:app --reload
```

启动后可访问：

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health Check: `http://127.0.0.1:8000/api/v1/health`

当前 API 路由覆盖：

- `/api/v1/health`
- `/api/v1/ingest`
- `/api/v1/query`
- `/api/v1/answers/generate`
- `/api/v1/documents`
- `/api/v1/traces`
- `/api/v1/stats`
- `/api/v1/collections`
- `/api/v1/evaluations`

### 2. 启动 Dashboard

Dashboard 依赖开发扩展中的 `streamlit`，因此需要先安装：

```bash
pip install -e ./backend[dev]
```

启动命令：

```bash
PYTHONPATH=backend/src python -m streamlit run backend/src/rag_mcp/observability/dashboard/app.py
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='backend/src'
python -m streamlit run backend/src/rag_mcp/observability/dashboard/app.py
```

如果你更希望使用仓库内脚本，也可以运行：

```powershell
.\scripts\start_dashboard.ps1
```

### 3. 启动 MCP stdio Server

这个入口是给 MCP Host / Client 调用的，不适合人直接在终端里交互输入。

```bash
PYTHONPATH=backend/src python -m rag_mcp.mcp.server
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='backend/src'
python -m rag_mcp.mcp.server
```

注意：

- 这是 `stdio` 协议服务
- 直接在终端里敲回车会触发 JSON-RPC 解析错误
- 如果你只是想验证功能，优先使用 FastAPI 或 Dashboard

## 快速开始

如果你的目标是“先把本地链路跑起来”，建议按这个顺序操作：

1. 创建并激活虚拟环境
2. 安装开发依赖：`pip install -e ./backend[dev]`
3. 复制配置模板：`config/settings.yaml.example -> config/settings.yaml`
4. 配置 `.env` 中的 API Key
5. 启动 FastAPI 或 Dashboard

最短调试路径通常是：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .\backend[dev]
Copy-Item .\config\settings.yaml.example .\config\settings.yaml
Copy-Item .\.env.example .\.env
$env:PYTHONPATH='backend/src'
uvicorn rag_mcp.main:app --reload
```

## 测试

安装开发依赖后，可在仓库根目录运行：

```bash
pytest
```

如果你需要更稳定地解析包路径，也可以显式设置：

```bash
PYTHONPATH=backend/src pytest
```

Windows PowerShell:

```powershell
$env:PYTHONPATH='backend/src'
pytest
```

## 数据与本地产物

仓库当前会跟踪这些内容：

- `data/documents/` 下的示例文档
- `data/evaluations/golden_test_set.json` 评测样例

默认不会提交这些本地产物：

- `.env`
- `config/settings.yaml`
- `data/traces/`
- `data/vector_store/`
- 虚拟环境、缓存、IDE 配置

## 文档

补充资料见：

- [技术文档](</d:/PersonalProject/RAG-MCP/docs/技术文档.md>)
- [重构规划](</d:/PersonalProject/RAG-MCP/docs/RESTRUCTURE_PLAN.md>)

## 当前说明

当前仓库主维护对象是 `backend/` 这套实现。仓库中的本地配置、向量索引、trace、缓存文件均视为运行产物，不属于源码的一部分。
