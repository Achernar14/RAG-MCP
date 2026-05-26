# FlyGPT 与 RAG-MCP 对比分析

## 概述

本文档对比两个项目的定位、架构、功能和技术栈，帮助开发者理解两者的差异和适用场景。

---

## 1. 项目定位对比

| 维度 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **核心定位** | 全功能 AI 助手平台 | 专业化 RAG 服务与知识上下文层 |
| **应用场景** | 企业级 AI 应用集成平台 | AI Agent / MCP Client 的知识增强服务 |
| **架构风格** | 单体应用 (Monolithic) | 模块化微服务 (Modular Microservice) |
| **服务范围** | 全栈解决方案 (前端+后端+多服务) | 专注 RAG 能力输出 |

**关键区别：**
- **FlyGPT** 是一个"平台"，提供从用户认证、API 网关到 AI 能力的全栈服务
- **RAG-MCP** 是一个"能力层"，专注于提供可复用的 RAG 能力

---

## 2. 技术栈对比

### 2.1 核心框架

| 组件 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **编程语言** | Python | Python |
| **Web 框架** | FastAPI | FastAPI (REST) + MCP SDK (stdio) |
| **前端** | Vue.js | 静态 Dashboard HTML |
| **依赖管理** | uv | pyproject.toml + pip |
| **配置管理** | YAML 多环境配置 | settings.yaml + .env |

### 2.2 数据存储

| 组件 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **关系数据库** | PostgreSQL (with pgvector) | 无 (JSON 文件存储) |
| **缓存/消息队列** | Redis Streams | 无 |
| **向量存储** | PostgreSQL/pgvector | Chroma (本地持久化) |
| **稀疏索引** | 未明确 | BM25 (JSON 持久化) |
| **文档存储** | 数据库表 | JSON 文件 |

**关键区别：**
- **FlyGPT** 采用传统数据库中心架构，支持大规模分布式部署
- **RAG-MCP** 采用轻量级本地存储，适合本地部署和边缘场景

### 2.3 AI 模型集成

| 能力 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **Embedding** | 集成在 RAG 组件中 | 可插拔 Provider (zhipu, hash) |
| **LLM** | 集成在 Agent 框架中 | 可插拔 Provider (deepseek, stub) |
| **Rerank** | 未明确 | 可插拔 Provider (lexical) |
| **Vision** | 未明确 | 骨架已预留，默认禁用 |

---

## 3. 架构设计对比

### 3.1 FlyGPT 架构

```
FlyGPT (单体应用)
├── Web 层 (Vue 前端 + FastAPI 后端)
├── 控制器层 (admin/console/service_api/web)
├── 业务层 (services)
├── 组件层 (components)
│   ├── RAG 组件
│   ├── 工作流组件
│   ├── 安全组件
│   └── 配置中心/服务发现
├── 数据层 (models + repositories)
├── 中间件 (middleware)
├── 监听器 (listeners - Redis Streams)
└── 定时任务 (tasks - APScheduler)
```

**特点：**
- 分层架构，职责清晰
- 组件化设计，RAG 作为其中一个组件
- 多服务运行模式 (Web服务器/调度器/监听器)
- 适合企业级多租户场景

### 3.2 RAG-MCP 架构

```
RAG-MCP (模块化服务)
├── 协议层 (Presentation)
│   ├── MCP Server (stdio)
│   └── REST API (FastAPI)
├── 应用层 (Application)
│   ├── Ingest Use Cases
│   ├── Query Use Cases
│   ├── Answer Generation Use Cases
│   └── Management Use Cases
├── 领域层 (Domain)
│   ├── Entities / Value Objects
│   ├── Services (Retrieval/Generation/Evaluation)
│   └── Repository Interfaces
└── 基础设施层 (Infrastructure)
    ├── Providers (Embedding/LLM/Rerank/Vision)
    ├── Vector Stores (Chroma)
    ├── Sparse Index (BM25)
    ├── Loaders / Splitters
    └── Repositories (JSON/JSONL)
```

**特点：**
- 严格的分层架构 (DDD 风格)
- 协议层薄化，应用层厚实
- 一切能力可插拔 (Provider 模式)
- 专注 RAG 主业，边界清晰

---

## 4. 功能对比

### 4.1 RAG 核心能力

| 功能 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **文档摄取** | 支持 (集成在监听器) | 支持 (Markdown/TXT/PDF) |
| **向量检索** | 支持 (pgvector) | 支持 (Chroma + Dense Retrieval) |
| **稀疏检索** | 未明确 | 支持 (BM25) |
| **混合检索** | 未明确 | 支持 (RRF Fusion) |
| **重排序** | 未明确 | 支持 (Lexical Rerank) |
| **溯源** | 支持 | 支持 (详细 SourceTrace) |
| **多模态** | 未明确 | 骨架已预留 |

### 4.2 可观测性

| 功能 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **日志管理** | 统一日志格式，支持分割 | Trace 持久化 (JSONL) |
| **监控** | 内置系统监控 | Trace 详情、阶段耗时 |
| **调试界面** | 控制台管理 | Dashboard (6页) |
| **评测体系** | 未明确 | Golden Test Set + HitRate/MRR |

### 4.3 协议暴露

| 协议 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **REST API** | 支持 (多端点) | 支持 (统一 API) |
| **MCP** | 未支持 | 支持 (stdio + SDK) |
| **WebSocket** | 支持 | 未支持 |
| **SSE** | 支持 | 未支持 |

---

## 5. 部署对比

### 5.1 部署复杂度

| 维度 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **依赖** | PostgreSQL + Redis + C++ 编译 | 仅 Python 环境 |
| **配置** | 多环境 YAML 配置 | settings.yaml + .env |
| **启动** | 三个独立服务 | 单一服务 |
| **容器化** | Docker + Kubernetes 支持 | Docker 支持 |

### 5.2 适用场景

| 场景 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **本地开发** | 较复杂 (需数据库) | 简单 (开箱即用) |
| **企业部署** | 适合 | 可用但需扩展 |
| **边缘部署** | 过重 | 适合 |
| **AI Agent 集成** | 通过 API | 通过 MCP (原生) |

---

## 6. 开发体验对比

### 6.1 FlyGPT 开发体验

**优点：**
- 完整的开发工具链 (pre-commit, ruff, pytest)
- 统一脚本系统 (uv run)
- C++ 扩展支持高性能场景
- 完善的文档和团队协作指南
- GitLab CI/CD 集成

**挑战：**
- 学习曲线陡峭 (需理解全栈架构)
- 本地开发环境搭建复杂 (需数据库)
- 代码库庞大，修改成本高

### 6.2 RAG-MCP 开发体验

**优点：**
- 架构清晰，边界明确
- 可插拔设计，扩展容易
- 轻量级本地开发
- 完整的技术文档指导
- 56+ 测试用例覆盖

**挑战：**
- 功能仍在迭代中 (85% 完成度)
- 多模态等高级功能未实现
- 缺少生产级部署验证

---

## 7. 代码组织对比

### 7.1 FlyGPT 目录结构

```
flygpt/
├── flygpt/              # 主模块
│   ├── controllers/     # 多层 API 控制器
│   ├── services/        # 业务服务
│   ├── components/      # 可插拔组件
│   ├── models/          # 数据库模型
│   └── middleware/      # 中间件
├── web/                 # Vue 前端
├── config/              # 配置文件
├── tests/               # 测试
└── scripts/             # 部署脚本
```

### 7.2 RAG-MCP 目录结构

```
RAG-MCP/
├── backend/
│   └── src/rag_mcp/
│       ├── mcp/         # 协议层
│       ├── application/ # 应用层
│       ├── domain/      # 领域层
│       ├── infrastructure/ # 基础设施层
│       └── api/         # REST API
├── config/              # 配置
├── data/                # 数据存储
├── docs/                # 文档
└── tests/               # 测试
```

---

## 8. 适用场景推荐

### 8.1 选择 FlyGPT 的场景

- 需要构建企业级 AI 应用平台
- 需要多租户、权限管理、服务发现等企业功能
- 有完整的运维团队和基础设施
- 需要工作流引擎、Agent 框架等扩展能力
- 已有 PostgreSQL/Redis 基础设施

### 8.2 选择 RAG-MCP 的场景

- 需要 AI Agent 知识增强 (通过 MCP)
- 本地或边缘部署场景
- 快速原型开发或 POC 验证
- 需要深度定制 RAG 行为
- 希望保持架构简单和可维护性

### 8.3 组合使用场景

- **FlyGPT 作为主平台**：处理用户认证、API 网关、业务编排
- **RAG-MCP 作为知识服务**：通过 MCP 协议为 FlyGPT 的 Agent 提供知识上下文

---

## 9. 迁移建议

### 9.1 从 RAG-MCP 到 FlyGPT

如果需要将 RAG-MCP 的能力集成到 FlyGPT：

1. **Provider 层迁移**：将 Embedding/LLM Provider 集成到 FlyGPT 的组件系统
2. **Use Case 层迁移**：将应用层逻辑封装为 FlyGPT Service
3. **协议层适配**：通过 REST API 或内部服务调用集成

### 9.2 从 FlyGPT 到 RAG-MCP

如果需要从 FlyGPT 迁移 RAG 功能到 RAG-MCP：

1. **数据迁移**：导出向量数据到 Chroma 格式
2. **配置迁移**：转换配置文件格式
3. **接口适配**：通过 MCP 或 REST API 调用

---

## 10. 总结

| 维度 | FlyGPT | RAG-MCP |
|------|--------|---------|
| **定位** | 全功能平台 | 专业化服务 |
| **复杂度** | 高 | 中 |
| **灵活性** | 中 (需改代码) | 高 (可插拔) |
| **生产就绪** | 是 | 部分就绪 |
| **本地友好** | 否 | 是 |
| **AI Agent 友好** | 通过 API | 通过 MCP (原生) |

**核心建议：**
- 如果需要**企业级 AI 平台**，选择 **FlyGPT**
- 如果需要**AI Agent 知识服务**，选择 **RAG-MCP**
- 两者可以**互补使用**，各自发挥优势
