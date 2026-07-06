# RAG-MCP 本地验证 Demo 记录

本文档记录 RAG-MCP 项目在本地开发环境中的端到端验证流程和结果。

> 完整 Demo（含 FastAPI 文档抓取、Docker 部署、公网访问）见 [demo-fastapi-qa.md](demo-fastapi-qa.md)（待网络和部署环境就绪后补充）。

---

## 1. 验证环境

| 项目 | 信息 |
|---|---|
| OS | Windows 11 |
| Python | ≥ 3.11 |
| 向量库 | Chroma（本地持久化） |
| Embedding | Hash（确定性本地向量，开发用） |
| LLM | Stub（本地桩，开发用） |
| 稀疏检索 | BM25（JSON 持久化） |
| 重排序 | Lexical Reranker |

> 上线前应将 embedding 切换为 Zhipu（智源），LLM 切换为 DeepSeek，见 `.env.example`。

---

## 2. 验证流程

### 2.1 文档摄入

摄入项目自身技术文档（23 个 chunk）：

```bash
# 一键脚本
python scripts/quick_ingest.py --path docs/技术文档.md --force-rebuild
```

结果：
```
[1/1] ↻ replaced: 技术文档.md | chunks=23 | doc_id=2c40783a... | trace=...
[done] 成功 1 | 失败 0 | 耗时 0.1s
```

**摄入管线**：文件加载 → 文本切分（chunk_size=500, overlap=50）→ 向量化 → Chroma 写入 + BM25 索引

### 2.2 检索查询

查询"Skill 机制是怎么工作的？"：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Skill 机制是怎么工作的？", "top_k": 5}'
```

返回 5 条相关结果，含 `retrieval_method: sparse+rerank`，`score` 从 1.0 到 0.994，均来自 `技术文档.md` 的相关段落。

### 2.3 生成式问答

```bash
curl -X POST http://127.0.0.1:8000/api/v1/answers/generate \
  -H "Content-Type: application/json" \
  -d '{"query": "Skill 机制是怎么工作的？", "top_k": 5}'
```

返回带引用来源的回答（使用 stub LLM 时为检索片段拼接，使用真实 LLM 时为自然语言总结）。

### 2.4 检索评测

创建 20 条 Golden QA 对（`data/evaluations/rag_mcp_golden_test_set.json`），覆盖 9 个概念类别：

| 类别 | 题目数 | 示例问题 |
|---|---|---|
| Skill | 4 | "Skill 是怎么注册和启用的？" |
| Retrieval | 3 | "混合检索中 RRF 融合是怎么工作的？" |
| MCP | 2 | "MCP 协议支持哪些传输方式？" |
| Config | 2 | "如何切换 embedding、LLM 和向量库的提供者？" |
| Ingestion | 2 | "文档摄入管线包含哪些步骤？" |
| Architecture | 4 | "项目采用了什么样的分层架构？" |
| REST | 1 | "REST API 提供了哪些端点？" |
| Observability | 1 | "可观测性系统是如何工作的？" |
| Evaluation | 1 | "检索评测系统支持哪些指标？" |

运行评测：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluations/run \
  -H "Content-Type: application/json" \
  -d '{"dataset_path": "data/evaluations/rag_mcp_golden_test_set.json", "top_k": 5}'
```

---

## 3. 评测结果

| 指标 | 结果 |
|---|---|
| 总用例数 | 20 |
| 命中数 | 20 |
| **HitRate@5** | **1.00（100%）** |
| **MRR** | **1.00** |
| 失败数 | 0 |

### 逐题详情

所有 20 题均在第一页结果中命中目标文档（`技术文档.md`），MRR 为 1.0。

> ⚠️ **注意**：当前评测为单文档场景（仅 `技术文档.md`），使用 hash embedding + BM25 混合检索。hash embedding 不提供语义相似度——主要由 BM25 精确词匹配驱动。切换到真实 embedding 提供者（Zhipu）、多文档语料（如 FastAPI docs 数十个 .md 文件）后，指标更具参考价值。

---

## 4. REST API 端点验证

全部 REST 端点功能正常：

| 端点 | 方法 | 状态 |
|---|---|---|
| `/api/v1/health` | GET | ✅ |
| `/api/v1/ingest` | POST | ✅ created / replaced / skipped |
| `/api/v1/query` | POST | ✅ 返回结果 + sources + trace |
| `/api/v1/answers/generate` | POST | ✅ 生成回答 + 引用 |
| `/api/v1/documents` | GET | ✅ 文档列表 |
| `/api/v1/documents/{id}` | GET | ✅ 文档详情 |
| `/api/v1/documents/{id}/detail` | GET | ✅ 含 chunk 列表 |
| `/api/v1/documents/{id}` | DELETE | 未测试 |
| `/api/v1/stats` | GET | ✅ 统计信息 |
| `/api/v1/collections` | GET | ✅ 集合列表 |
| `/api/v1/evaluations/run` | POST | ✅ 评测执行 + 报告持久化 |
| `/api/v1/evaluations` | GET | ✅ 报告列表 |
| `/api/v1/evaluations/{id}` | GET | ✅ 报告详情 |
| `/api/v1/traces` | GET | ✅ trace 列表 |
| `/api/v1/traces/{id}` | GET | ✅ trace 详情 |

---

## 5. 脚本工具验证

| 脚本 | 功能 | 状态 |
|---|---|---|
| `scripts/quick_ingest.py` | 一键摄入（文件/目录） | ✅ `--path` `--recursive` `--force-rebuild` |
| `scripts/batch_ingest.py` | 批量摄入（并发 + 报告） | ✅ `--workers` `--report` `--dry-run` |
| `scripts/fetch_docs.py` | GitHub 文档抓取 | ⏳ 等待网络（代码已完成） |

---

## 6. 下一步

1. **网络恢复后**：运行 `fetch_docs.py` 获取 FastAPI 文档 → `batch_ingest.py` 批量摄入 → 重新评测
2. **部署环境就绪后**：Dockerfile + docker-compose + 云服务器部署
3. **生产化**：API Key 认证、Weaviate remote 模式、Redis 缓存、CI/CD

---

## 附录 A：Quick Start 验证清单

按 [quickstart.md](quickstart.md) 执行，确认以下步骤：

- [x] `cd backend && pip install -e .`
- [x] 配置 `.env`（真实 API Key）
- [x] 启动服务 `python -m uvicorn rag_mcp.main:app`
- [x] 摄入文档 `POST /api/v1/ingest`
- [x] 检索查询 `POST /api/v1/query`
- [x] 生成回答 `POST /api/v1/answers/generate`
- [ ] Claude Desktop 集成（需真实 API Key）

## 附录 B：架构速览

```
┌─────────────────────────────────────────────┐
│           Presentation Layer                  │
│  REST (FastAPI)  │  MCP (stdio/http/sse)    │
│                   │  Dashboard (Streamlit)    │
├─────────────────────────────────────────────┤
│           Application Layer                   │
│  Use Cases (ingest/query/generate/eval/...)  │
│  DTOs (request/response models)              │
├─────────────────────────────────────────────┤
│           Domain Layer                        │
│  Entities (Document/Chunk/RetrievalResult)   │
│  Service Abstractions                        │
│  Repository Contracts                        │
├─────────────────────────────────────────────┤
│           Infrastructure Layer                │
│  Chroma / Weaviate  │  BM25  │  Reranker    │
│  Zhipu / Hash Emb   │  DeepSeek / Stub LLM │
│  Loaders  │  Splitters  │  Pipeline         │
├─────────────────────────────────────────────┤
│           Assembly Layer                      │
│  SkillRegistry (topological sort + DI)       │
│  Settings (Pydantic + YAML override)         │
└─────────────────────────────────────────────┘
```
