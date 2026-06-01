# RAG-MCP

> 面向本地知识库与 AI Agent 集成场景的模块化 RAG 服务

本项目由华南师范大学软件学院的龙成飞（@longjincf）、曾博源（@Achernar14）完成。

## 项目定位

RAG-MCP 是一个"面向 AI Agent / MCP Client 的知识上下文服务层与 RAG 能力底座"，聚焦三类能力：

- **文档摄取** — 支持 `txt`、`md`、`pdf` 的加载、切分、向量化与索引
- **检索与问答** — 混合 Dense + Sparse 检索、RRF 融合、Rerank、生成式问答
- **可观测性** — Trace 收集、Dashboard、评测体系

通过 REST API 和 **MCP Streamable HTTP** 协议暴露能力，可独立运行，也可作为 AI Agent 的知识后端。

## 传输协议

RAG-MCP 支持三种 MCP 传输方式，通过 `config/settings.yaml` 中的 `mcp.transport` 配置：

| 传输方式             | 说明                               | 适用场景              |
| ---------------- | -------------------------------- | ----------------- |
| `streamable-http` | **推荐** — MCP 官方新一代 HTTP 传输，支持远程访问 | 生产部署、远程 Agent 接入  |
| `stdio`          | 标准输入输出，本地进程通信                     | 本地开发、IDE 集成       |
| `sse`            | Server-Sent Events（旧版 HTTP 传输）    | 兼容旧版 MCP Client  |

### MCP Streamable HTTP 模式（推荐）

启动后，MCP 服务自动挂载在 FastAPI 的 `/mcp` 路径下，与 REST API 共存：

```bash
# 启动统一服务（REST API + MCP HTTP）
PYTHONPATH=backend/src uvicorn rag_mcp.main:app --host 127.0.0.1 --port 8000

# MCP 端点: http://127.0.0.1:8000/mcp
# REST 端点: http://127.0.0.1:8000/api/v1/*
```

### MCP stdio 模式

```bash
# 通过命令行参数指定传输
python -m rag_mcp.mcp.server --transport stdio
```

### MCP 独立 HTTP 模式

```bash
# 独立运行 MCP 服务器（不依赖 FastAPI）
python -m rag_mcp.mcp.server --transport streamable-http
```

## 项目结构

```text
RAG-MCP/
├── backend/src/rag_mcp/        # 主代码
│   ├── core/                   # 容器、配置、异常、Skill 注册
│   ├── skills/                 # 6 个 Skill 模块（ingestion / retrieval / generation / ...）
│   ├── application/use_cases/  # Use Case 编排层
│   ├── domain/                 # 领域实体、服务、抽象接口
│   ├── infrastructure/         # Provider 实现、存储、缓存
│   ├── mcp/                    # MCP Server（stdio / streamable-http / sse）
│   ├── api/                    # REST API 路由
│   └── observability/          # Dashboard
├── config/                     # 配置文件与 Prompt 模板
├── data/                       # 示例文档与评测集
├── docs/                       # 设计文档与指南
├── tests/                      # 单元测试
└── scripts/                    # 启动脚本
```

## Skill 架构

项目采用模块化 Skill 架构，6 个 Skill 可独立开关：


| Skill                   | MCP 工具                                                                             | 依赖          |
| ----------------------- | ---------------------------------------------------------------------------------- | ----------- |
| **ingestion**           | `knowledge_ingest`, `knowledge_status`, `rebuild_collection`, `list_collections`   | —           |
| **retrieval**           | `knowledge_query`                                                                  | → ingestion |
| **generation**          | `generate_answer`                                                                  | → retrieval |
| **document_management** | `list_documents`, `get_document_detail`, `get_document_summary`, `delete_document` | —           |
| **evaluation**          | `run_evaluation`, `list_evaluation_reports`, `get_evaluation_report`               | → retrieval |
| **observability**       | `list_traces`, `get_trace_detail`                                                  | —           |


通过 `config/settings.yaml` 中的 `skills:` 配置节控制开关。

## 快速开始

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./backend[dev]
cp config/settings.yaml.example config/settings.yaml
cp .env.example .env
# 编辑 .env 填入 API Key
PYTHONPATH=backend/src uvicorn rag_mcp.main:app --reload
```

> 详细的安装、配置和启动说明见 [安装与运行指南](docs/setup-and-operations.md)。

## MCP 配置

在 `config/settings.yaml` 中配置 MCP 传输：

```yaml
mcp:
  server_name: "rag-mcp"
  server_version: "0.1.0"
  transport: "streamable-http"  # "stdio" | "streamable-http" | "sse"
  host: "127.0.0.1"
  port: 9000
  mount_path: "/mcp"            # HTTP 传输的 URL 挂载路径
```

## 文档索引


| 文档                                                  | 内容                |
| --------------------------------------------------- | ----------------- |
| [安装与运行指南](docs/setup-and-operations.md)             | 环境搭建、配置说明、三种启动方式  |
| [技术文档](docs/技术文档.md)                                | 架构设计、模块职责、开发规范    |
| [Skill 架构详解](docs/guides/skill-architecture.md)     | Skill 模块化组装机制     |
| [Skill 化架构规划](docs/skill_architecture_plan.md)      | 内外部 Skill 划分与接入计划 |
| [补全路线图](docs/roadmap.md)                            | 后续开发优先级与实施计划      |
| [Redis 接入方案](docs/redis_integration_plan.md)        | 缓存层设计与实现          |
| [FlyGPT 对比分析](docs/flygpt_vs_rag-mcp_comparison.md) | 两项目定位与架构差异        |
| [MCP 协议指南](docs/guides/mcp-protocol.md)             | MCP 协议层实现         |


## 许可

本项目的许可证信息详见仓库根目录的 LICENSE 文件。
