# 安装、配置与运行指南

本文档覆盖 RAG-MCP 的环境搭建、配置说明和三种启动方式。

---

## 一、环境要求

- Python `3.11+`
- 建议使用虚拟环境
- Windows PowerShell、macOS/Linux shell 均可运行

---

## 二、安装

### 2.1 创建虚拟环境

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

> **注意**: 在 Ubuntu/Debian 系统上，如果提示 `ensurepip is not available`，需要先安装 `python3-venv`：
>
> ```bash
> sudo apt install python3.venv
> ```

**Windows PowerShell:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2.2 安装依赖

本项目使用 `backend/pyproject.toml` 作为依赖入口。

仅安装后端运行依赖：

```bash
pip install -e ./backend
```

安装开发依赖（包含 `pytest` 和 `streamlit`）：

```bash
pip install -e ./backend[dev]
```

安装 Redis 缓存支持（可选）：

```bash
pip install -e "./backend[redis]"
```

---

## 三、配置

### 3.1 初始化配置文件

**Linux / macOS:**

```bash
cp config/settings.yaml.example config/settings.yaml
cp .env.example .env
```

**Windows PowerShell:**

```powershell
Copy-Item .\config\settings.yaml.example .\config\settings.yaml
Copy-Item .\.env.example .\.env
```

### 3.2 配置项说明

| 配置节 | 说明 |
|--------|------|
| `embedding` / `embedding_provider` | 向量化 Provider 选择与连接参数 |
| `llm` | LLM Provider 选择与连接参数 |
| `vector_store` | 向量存储选择（chroma / weaviate / memory） |
| `ingestion` | 文档摄取参数（chunk_size、overlap、文件类型等） |
| `retrieval` | 检索参数（top_k、rerank 开关等） |
| `rerank` | 重排序 Provider 配置 |
| `observability` | Trace 开关与路径 |
| `evaluation` | 评测开关与评测集路径 |
| `prompts` | Prompt 模板路径 |
| `api` | REST API 主机与端口 |
| `redis` | Redis 缓存配置（可选） |
| `skills` | Skill 模块开关 |

默认模板中的路径约定：

- 向量库路径：`data/vector_store/chroma_live`
- trace 路径：`data/traces/traces.jsonl`
- 评测报告路径：`data/evaluations/reports.jsonl`

**注意：**

- `config/settings.yaml` 属于本地运行配置，默认不提交到仓库
- `.env` 用于保存密钥和环境变量，默认不提交到仓库
- `settings.yaml` 存储环境变量**名**（如 `api_key_env: "ZHIPU_API_KEY"`），不存储真实密钥

---

## 四、启动方式

### 4.1 FastAPI 服务

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

### 4.2 Dashboard

依赖开发依赖中的 `streamlit`：

```bash
pip install -e ./backend[dev]
PYTHONPATH=backend/src python -m streamlit run backend/src/rag_mcp/observability/dashboard/app.py
```

也可以使用脚本：

```bash
# Linux / macOS
bash scripts/start_dashboard.sh

# Windows PowerShell
.\scripts\start_dashboard.ps1
```

### 4.3 MCP stdio Server

给 MCP Host / Client 调用，不适合人在终端直接交互。

```bash
PYTHONPATH=backend/src python -m rag_mcp.mcp.server
```

---

## 五、测试

安装开发依赖后，在仓库根目录运行：

```bash
pytest
```

显式指定包路径：

```bash
PYTHONPATH=backend/src pytest
```

---

## 六、数据与本地产物

仓库跟踪的内容：

- `data/documents/` 下的示例文档
- `data/evaluations/golden_test_set.json` 评测样例

默认不提交的运行产物：

- `.env`、`config/settings.yaml`
- `data/traces/`、`data/vector_store/`
- 虚拟环境、缓存、IDE 配置
