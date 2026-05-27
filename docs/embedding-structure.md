# RAG-MCP Embedding 结构解析

## 1. 架构总览

```
┌─────────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Document    │────▶│   Splitter   │────▶│   Embedding   │────▶│  Vector Store    │────▶│  Retrieval   │
│  Loader      │     │  (Chunking)  │     │   Provider    │     │  (Dense+Sparse)  │     │  + Rerank    │
│ .txt/.md/.pdf│     │  500字/50重叠 │     │  Zhipu/Hash   │     │  Chroma + BM25   │     │  RRF Fusion  │
└─────────────┘     └──────────────┘     └───────────────┘     └──────────────────┘     └──────────────┘
```

项目采用 **Hybrid Retrieval（混合检索）** 架构，同时维护 **Dense（稠密向量）** 和 **Sparse（稀疏向量 BM25）** 两路索引，通过 **RRF（Reciprocal Rank Fusion）** 融合排序，再经过 **Reranker** 精排后返回最终结果。

---

## 2. Embedding Provider（向量生成）

项目定义了 `EmbeddingProvider` 抽象接口，提供两种实现：

### 2.1 Zhipu Embedding（生产环境）

| 配置项 | 值 |
|---|---|
| 接口 | `https://open.bigmodel.cn/api/paas/v4/embeddings` |
| 模型 | `embedding-3` |
| 维度 | **2048** |
| 超时 | 30s |
| 协议 | OpenAI 兼容格式 |

实现位置：`backend/src/rag_mcp/infrastructure/embedding/zhipu_embedding.py`

调用方式：逐条调用 API（非批量），每次 POST 发送 `{"model": "embedding-3", "input": <text>}`，从响应中提取 `data[0]["embedding"]`。

### 2.2 Hash Embedding（开发/测试）

| 配置项 | 值 |
|---|---|
| 算法 | SHA-256 哈希 |
| 维度 | **64**（可配置） |
| 外部依赖 | 无 |

实现位置：`backend/src/rag_mcp/infrastructure/embedding/hash_embedding.py`

生成方式：对文本做 SHA-256 摘要，将字节循环映射为 `[0, 1)` 浮点数向量。确定性输出，用于离线测试。

### 2.3 抽象接口

```python
# domain/repositories/contracts.py
class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
```

通过 `infrastructure/providers/factories.py` 中的 `create_embedding_provider(settings)` 工厂方法，根据配置 `embedding.provider` 值（`zhipu` / `hash`）实例化对应实现。

---

## 3. 文档分块（Chunking）

实现位置：`backend/src/rag_mcp/infrastructure/splitters/simple_splitter.py`

### 3.1 分块参数

| 参数 | 值 | 说明 |
|---|---|---|
| `chunk_size` | 500 字符 | 滑动窗口大小 |
| `chunk_overlap` | 50 字符 | 块间重叠 |
| `boundary_scan_chars` | 80 字符 | 边界扫描范围 |
| `min_chunk_length` | 40 字符 | 最短有效块 |
| `preserve_paragraph_breaks` | true | 保留段落断行 |

### 3.2 分块算法

```
输入文本
  │
  ▼ 预处理：CRLF→LF, Tab→Space, 折叠多余空格, 保留段落断行
  │
  ▼ 滑动窗口：从位置 0 开始，每次取 chunk_size 字符
  │
  ▼ 边界优化：向后扫描 boundary_scan_chars，按优先级找断点
  │   1️⃣ 段落断行 (\n\n)
  │   2️⃣ 句末标点 (. ! ? 。！？)
  │   3️⃣ 空白/换行
  │
  ▼ 下一个窗口起点 = 当前终点 - chunk_overlap（对齐到非空白字符）
  │
  ▼ 过滤：丢弃短于 min_chunk_length 的块（除非是最后一块）
```

### 3.3 Chunk ID 格式

```
{document_id}:{chunk_index}
例如：abc123def:0, abc123def:1, abc123def:2
```

---

## 4. 向量存储（Vector Store）

### 4.1 Dense 存储 — ChromaDB

实现位置：`backend/src/rag_mcp/infrastructure/vector_store/chroma_store.py`

| 配置项 | 值 |
|---|---|
| 持久化路径 | `data/vector_store/chroma_live` |
| Collection | `rag_mcp_live` |
| 客户端 | `chromadb.PersistentClient` |

**写入**：`collection.upsert(ids, documents, embeddings, metadatas)`
- `ids`：chunk ID
- `documents`：chunk 文本
- `embeddings`：2048 维稠密向量
- `metadatas`：`{document_id, source_path, chunk_index}`

**查询**：`collection.query(query_embeddings, n_results)`
- 使用 Chroma 内置近似最近邻搜索
- 距离转相似度：`score = 1.0 / (1.0 + max(distance, 0.0))`
- 包含 SQLite 锁重试机制（最多 5 次，间隔 0.2s）

### 4.2 Sparse 存储 — BM25

实现位置：`backend/src/rag_mcp/infrastructure/sparse/bm25_store.py`

| 配置项 | 值 |
|---|---|
| 持久化文件 | `data/vector_store/bm25_index.json` |
| 算法 | Okapi BM25 |
| k1 | 1.5 |
| b | 0.75 |
| 分词 | `\w+` 正则（Unicode 感知） |

每个 chunk 存储：词频表、文档长度、文本、元数据。

### 4.3 元数据存储

| 数据 | 文件 | 说明 |
|---|---|---|
| Document 列表 | `data/vector_store/documents.json` | 文档元信息、指纹、统计 |
| Chunk 列表 | `data/vector_store/chunks.json` | 文本块内容及关联 |

### 4.4 In-Memory Store（开发/测试）

实现位置：`backend/src/rag_mcp/infrastructure/vector_store/memory_store.py`
- 纯 Python 字典存储，余弦相似度计算
- 无持久化，重启数据丢失

---

## 5. 检索流程（Retrieval Pipeline）

### 5.1 完整检索链路

```
Query: "用户问题"
  │
  ├──── 1. Query Embedding ────
  │     Zhipu API 将问题编码为 2048 维向量
  │
  ├──── 2. Dense Retrieval ────
  │     ChromaDB 向量近邻搜索 → top-5 结果（标记 "dense"）
  │
  ├──── 3. Sparse Retrieval ───
  │     BM25 关键词匹配 → top-5 结果（标记 "sparse"）
  │
  ├──── 4. RRF Fusion ─────────
  │     对两路结果做 Reciprocal Rank Fusion：
  │       score = Σ 1/(k + rank)，k=60
  │     归一化后截取 top-5（标记 "dense"/"sparse"/"dense+sparse"）
  │
  ├──── 5. Rerank ─────────────
  │     Lexical Reranker 基于词元重叠重排：
  │       score = overlap_count × 10 + original_score
  │     截取 top-5（标记追加 "+rerank"）
  │
  ▼
  返回 list[RetrievalResult]
  包含：chunk_id, score, text, metadata, retrieval_method
```

### 5.2 RRF 融合公式

```
对每个候选结果 r：
  fused_score(r) = Σ_{list ∈ dense, sparse}  1 / (rrf_k + rank_list(r))

其中 rrf_k = 60

最终分数归一化：score / max_score
```

同时出现在两路结果中的 chunk 会获得更高分数（两路贡献叠加），自动体现"双路命中"优势。

### 5.3 检索配置

| 参数 | 值 |
|---|---|
| `retrieval.top_k` | 5 |
| `retrieval.dense_top_k` | 5 |
| `retrieval.sparse_top_k` | 5 |
| `retrieval.hybrid_top_k` | 5 |
| `retrieval.rrf_k` | 60 |
| `retrieval.rerank_enabled` | true |
| `retrieval.rerank_top_k` | 5 |

---

## 6. Ingestion 完整流程

```
POST /api/v1/ingest {"path": "/path/to/file.pdf"}
  │
  ▼ 1. 校验文件
  │    扩展名支持（.txt/.md/.pdf）、大小 ≤20MB、非隐藏文件
  │
  ▼ 2. 幂等检查
  │    SHA-256 指纹比对，内容未变则跳过
  │
  ▼ 3. 加载文档
  │    .txt/.md → TextDocumentLoader
  │    .pdf     → PdfDocumentLoader (pypdf)
  │
  ▼ 4. 分块
  │    SimpleTextSplitter → list[Chunk]
  │
  ▼ 5. 生成 Embedding
  │    ZhipuEmbeddingProvider.embed_texts(chunk_texts)
  │    → 每块生成 2048 维向量
  │
  ▼ 6. 持久化
  │    ├─ documents.json   ← 文档元数据
  │    ├─ chunks.json      ← 块文本
  │    ├─ ChromaDB         ← 稠密向量索引
  │    └─ bm25_index.json  ← BM25 稀疏索引
```

---

## 7. 领域模型（核心数据结构）

```
Document
  ├── id: str                    # 文档唯一 ID
  ├── source_path: str           # 源文件路径
  ├── content: str               # 全文内容
  ├── fingerprints: dict         # SHA-256 指纹
  ├── metadata: dict             # 文件大小、词数、CJK 检测等
  └── created_at / updated_at

Chunk
  ├── id: str                    # 格式: {document_id}:{index}
  ├── document_id: str           # 所属文档
  ├── content: str               # 分块文本
  ├── chunk_index: int           # 块序号
  └── metadata: dict             # source_path, chunk_index

ChunkRecord
  ├── chunk_id: str
  ├── document_id: str
  ├── text: str
  ├── embedding: list[float]     # 2048 维向量
  └── metadata: dict

RetrievalResult
  ├── chunk_id: str
  ├── score: float               # 归一化相似度
  ├── text: str                  # 检索到的文本
  ├── metadata: dict
  └── retrieval_method: str      # "dense+sparse+rerank" 等
```

---

## 8. 配置体系

所有配置集中在 `config/settings.yaml`，通过 Pydantic 模型加载：

```yaml
embedding:
  provider: zhipu          # zhipu | hash
  dimensions: 2048

embedding_provider:
  api_base: https://open.bigmodel.cn/api/paas/v4
  model: embedding-3
  timeout_seconds: 30.0
  api_key_env: ZHIPU_API_KEY

vector_store:
  provider: chroma          # chroma | memory
  persist_path: data/vector_store/chroma_live
  collection_name: rag_mcp_live

ingestion:
  chunk_size: 500
  chunk_overlap: 50
  min_chunk_length: 40
  boundary_scan_chars: 80

retrieval:
  top_k: 5
  dense_top_k: 5
  sparse_top_k: 5
  hybrid_top_k: 5
  rrf_k: 60
  rerank_enabled: true
  rerank_top_k: 5
```

---

## 9. 关键依赖

| 包 | 版本 | 用途 |
|---|---|---|
| `chromadb` | ≥1.5.0 | 持久化向量数据库 |
| `httpx` | ≥0.27.0 | Zhipu/DeepSeek API 调用 |
| `pypdf` | ≥6.0.0 | PDF 文本提取 |
| `pydantic` | ≥2.11.0 | 配置校验与 DTO |
| `fastapi` | ≥0.115.0 | HTTP API 框架 |
| `mcp[cli]` | ≥1.27.0 | MCP 协议支持 |
