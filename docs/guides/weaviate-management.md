# RAG-MCP Weaviate 向量数据库管理手册

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                       RAG-MCP Application                       │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐  │
│  │  FastAPI      │    │  ApplicationContainer (container.py) │  │
│  │  /ingest      │───▶│                                      │  │
│  │  /query       │    │  provider="weaviate" ──┐             │  │
│  │  /answers     │    │                        ▼             │  │
│  └──────────────┘    │  ┌─────────────────────────────┐     │  │
│                      │  │  WeaviateVectorStore         │     │  │
│                      │  │  (weaviate_store.py)         │     │  │
│                      │  │                              │     │  │
│                      │  │  upsert()    ─ 写入向量       │     │  │
│                      │  │  query()     ─ 相似度检索     │     │  │
│                      │  │  delete_by_document() ─ 删除  │     │  │
│                      │  │  close()     ─ 关闭连接       │     │  │
│                      │  └──────────┬──────────────────┘     │  │
│                      └─────────────┼────────────────────────┘  │
│                                    │                            │
│                     ┌──────────────▼──────────────┐            │
│                     │  Weaviate Embedded 进程      │            │
│                     │  (Python 自动启停)            │            │
│                     │  bind: 127.0.0.1:8079        │            │
│                     │  数据: data/vector_store/     │            │
│                     │        weaviate/              │            │
│                     └──────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### 1.1 三路存储协作

```
                    ┌─────────────────────────────┐
                    │      Ingestion Pipeline      │
                    └──────┬──────────┬────────────┘
                           │          │
              ┌────────────▼──┐  ┌────▼──────────────┐
              │  Weaviate     │  │  BM25 JSON         │
              │  (dense 向量) │  │  (sparse 关键词)   │
              │              │  │                    │
              │  Cosine 相似 │  │  Okapi BM25        │
              │  HNSW 索引   │  │  词频 + 文档长度   │
              └──────┬───────┘  └─────┬──────────────┘
                     │               │
                     └───────┬───────┘
                             │
                    ┌────────▼─────────┐
                    │  RRF Fusion      │
                    │  (k=60)          │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Lexical Rerank  │
                    │  (token overlap) │
                    └─────────────────┘
```

### 1.2 数据文件布局

```
data/
├── documents/                          # 源文档
│   ├── sample.md
│   └── sample.pdf
├── evaluations/                        # 评估报告
└── vector_store/
    ├── weaviate/                       # ← Weaviate 数据目录（自动管理）
    │   └── (Weaviate 内部文件)
    ├── documents.json                  # 文档元数据索引
    ├── chunks.json                     # 分块文本 + 完整 metadata
    └── bm25_index.json                 # BM25 稀疏索引

~/.cache/weaviate-embedded/             # Weaviate binary 缓存（~100MB）
└── weaviate                            # 首次运行自动下载
```

---

## 2. 配置管理

### 2.1 完整配置项

```yaml
# config/settings.yaml
vector_store:
  # Provider 选择: "weaviate" | "chroma" | "memory"
  provider: "weaviate"

  # Weaviate Collection 名称（首字母大写）
  collection_name: "RAG_MCP"

  # ChromaDB 备用路径（provider=chroma 时生效）
  persist_path: "data/vector_store/chroma_live"

  # Weaviate Embedded 配置
  weaviate_persistence_data_path: "data/vector_store/weaviate"
  weaviate_version: "1.37.2"
  weaviate_hostname: "127.0.0.1"
  weaviate_port: 8079
```

### 2.2 配置项详解

| 配置项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `provider` | string | `"weaviate"` | 向量存储后端，三选一 |
| `collection_name` | string | `"RAG_MCP"` | Weaviate Collection 名，**必须首字母大写** |
| `persist_path` | string | `"data/vector_store/chroma"` | ChromaDB 专用，weaviate 模式下不影响 |
| `weaviate_persistence_data_path` | string | `"data/vector_store/weaviate"` | Weaviate 数据持久化目录 |
| `weaviate_version` | string | `"1.37.2"` | Embedded server 二进制版本 |
| `weaviate_hostname` | string | `"127.0.0.1"` | 绑定地址（仅本地回环） |
| `weaviate_port` | int | `8079` | REST 端口 |

### 2.3 Provider 切换

```yaml
# 方案 A: Weaviate（默认，生产推荐）
vector_store:
  provider: "weaviate"

# 方案 B: ChromaDB（旧方案回退）
vector_store:
  provider: "chroma"
  persist_path: "data/vector_store/chroma_live"
  collection_name: "rag_mcp_live"

# 方案 C: 内存模式（仅用于测试）
vector_store:
  provider: "memory"
```

切换后重启应用即可，无需其他改动。

---

## 3. 日常操作

### 3.1 启动与停止

**启动：** 应用启动时 Weaviate Embedded 自动启动，无需手动操作。

```bash
cd backend
source .venv/bin/activate
python -m rag_mcp.main   # Weaviate 随应用自动拉起
```

**停止：** 应用正常退出时 Weaviate 子进程自动关闭。

```bash
# 正常退出（Ctrl+C 或 SIGTERM）
# Weaviate 子进程随主进程退出，数据已持久化到磁盘
```

**异常退出处理：**

如果应用被 `kill -9` 强杀，Weaviate 子进程可能残留：

```bash
# 检查残留进程
ps aux | grep weaviate

# 清理残留（如果有）
pkill -f weaviate-embedded
```

### 3.2 数据导入（Ingest）

```bash
# 通过 API 导入单个文件
curl -X POST http://127.0.0.1:8000/api/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/document.pdf"}'

# 通过 API 批量导入
for f in /path/to/docs/*.md; do
  curl -s -X POST http://127.0.0.1:8000/api/v1/ingest \
    -H "Content-Type: application/json" \
    -d "{\"path\": \"$f\"}"
done
```

### 3.3 查询（Query）

```bash
# 基础查询
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "如何配置向量数据库", "top_k": 5}'

# 生成回答
curl -X POST http://127.0.0.1:8000/api/v1/answers/generate \
  -H "Content-Type: application/json" \
  -d '{"query": "如何配置向量数据库", "top_k": 5}'
```

### 3.4 查看状态

```bash
# 知识库状态
curl http://127.0.0.1:8000/api/v1/knowledge/status

# Collection 列表
curl http://127.0.0.1:8000/api/v1/collections

# 文档列表
curl http://127.0.0.1:8000/api/v1/documents
```

### 3.5 删除文档

```bash
# 删除指定文档（同时清理 Weaviate + BM25 + JSON 索引）
curl -X DELETE http://127.0.0.1:8000/api/v1/documents/{document_id}
```

---

## 4. 数据迁移

### 4.1 从 ChromaDB 迁移到 Weaviate

```bash
cd backend
source .venv/bin/activate

python ../scripts/migrate_chroma_to_weaviate.py \
    --chroma-path ../data/vector_store/chroma_live \
    --chroma-collection rag_mcp_live \
    --weaviate-data-path ../data/vector_store/weaviate \
    --weaviate-collection RAG_MCP
```

**迁移后验证：**

```bash
# 启动应用，执行查询确认数据可检索
curl -X POST http://127.0.0.1:8000/api/v1/query \
  -d '{"query": "测试查询", "top_k": 3}'
```

### 4.2 回退到 ChromaDB

```yaml
# config/settings.yaml
vector_store:
  provider: "chroma"
  persist_path: "data/vector_store/chroma_live"
  collection_name: "rag_mcp_live"
```

重启应用即可。如果 ChromaDB 数据仍保留在 `data/vector_store/chroma_live/`，无需重新导入。

---

## 5. 备份与恢复

### 5.1 备份

```bash
# 备份全部数据（Weaviate + JSON 元数据 + BM25 索引）
tar czf rag_mcp_backup_$(date +%Y%m%d).tar.gz \
    data/vector_store/weaviate/ \
    data/vector_store/documents.json \
    data/vector_store/chunks.json \
    data/vector_store/bm25_index.json

# 仅备份元数据（不含向量数据，体积更小）
tar czf rag_mcp_meta_$(date +%Y%m%d).tar.gz \
    data/vector_store/documents.json \
    data/vector_store/chunks.json \
    data/vector_store/bm25_index.json
```

### 5.2 恢复

```bash
# 停止应用
# kill <pid> 或 Ctrl+C

# 恢复数据
tar xzf rag_mcp_backup_YYYYMMDD.tar.gz

# 重启应用
python -m rag_mcp.main
```

### 5.3 从零重建

如果 Weaviate 数据损坏，可从源文档完全重建：

```bash
# 1. 清空向量数据
rm -rf data/vector_store/weaviate/

# 2. 清空元数据（可选）
rm -f data/vector_store/documents.json \
      data/vector_store/chunks.json \
      data/vector_store/bm25_index.json

# 3. 重新导入所有文档
for f in /path/to/docs/*; do
  curl -s -X POST http://127.0.0.1:8000/api/v1/ingest \
    -H "Content-Type: application/json" \
    -d "{\"path\": \"$f\"}"
done
```

---

## 6. 监控与诊断

### 6.1 健康检查

```bash
# 应用健康
curl http://127.0.0.1:8000/api/v1/knowledge/status

# Weaviate 进程状态
ps aux | grep weaviate

# 磁盘占用
du -sh data/vector_store/weaviate/
du -sh data/vector_store/
```

### 6.2 数据统计

```bash
# 文档数量
cat data/vector_store/documents.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'文档数: {len(d)}')"

# 分块数量
cat data/vector_store/chunks.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'分块数: {len(d)}')"

# BM25 索引大小
ls -lh data/vector_store/bm25_index.json
```

### 6.3 日志排查

```bash
# 应用日志（含 Weaviate 启动信息）
python -m rag_mcp.main 2>&1 | grep -i weaviate

# Trace 日志（每次查询的详细链路）
cat data/traces/traces.jsonl | python3 -m json.tool | tail -100
```

### 6.4 常见问题排查

| 现象 | 原因 | 解决方案 |
|---|---|---|
| 启动报错 `Weaviate Embedded 启动失败` | 首次运行网络不可达，无法下载 binary | 预下载 binary 到 `~/.cache/weaviate-embedded/` |
| 查询返回空结果 | Collection 为空或数据未写入 | 检查 `documents.json` 是否有数据，重新 ingest |
| 端口 8079 被占用 | 上次异常退出残留 Weaviate 进程 | `pkill -f weaviate-embedded` |
| `database is locked` 错误 | 不应出现（Weaviate 无 SQLite） | 确认 `provider` 不是 `chroma` |
| 子进程残留 | 应用被 `kill -9` 强杀 | `pkill -f weaviate-embedded`，考虑加 `atexit` 兜底 |

---

## 7. 性能调优

### 7.1 Collection 级别

Weaviate Collection 在首次创建时确定 HNSW 参数，后续无法修改。如需调整，需删除 Collection 重建。

当前配置（代码内置）：

```python
Configure.VectorIndex.hnsw(
    distance_metric=VectorDistances.COSINE,  # 余弦距离
    # 默认 HNSW 参数: ef=128, ef_construction=256, max_connections=64
)
```

### 7.2 Batch 写入

- 当前批量大小：200 条/批
- 可在 `weaviate_store.py` 的 `batch_size` 参数调整
- 建议范围：100-500，取决于文档大小和内存

### 7.3 查询性能

```yaml
# config/settings.yaml
retrieval:
  top_k: 5            # 最终返回数
  dense_top_k: 5      # Weaviate 召回数
  sparse_top_k: 5     # BM25 召回数
  hybrid_top_k: 5     # RRF 融合后保留数
  rerank_top_k: 5     # Rerank 后保留数
```

- 增大 `dense_top_k` 可提高召回率，但增加延迟
- 通常 `top_k = dense_top_k = sparse_top_k = 5` 即可满足大多数场景

---

## 8. 安全注意事项

### 8.1 网络隔离

- Weaviate Embedded 绑定 `127.0.0.1:8079`，仅本地回环可访问
- 外部无法直接连接 Weaviate 端口
- 所有外部访问通过 FastAPI 的 `127.0.0.1:8000` 端口代理

### 8.2 数据安全

- Weaviate 数据目录 `data/vector_store/weaviate/` 包含向量数据
- `documents.json` 和 `chunks.json` 包含文档原文
- 备份时需一并打包所有数据文件
- 不应将数据目录纳入版本控制（已在 `.gitignore` 中排除）

### 8.3 Binary 安全

- Weaviate binary 缓存在 `~/.cache/weaviate-embedded/`
- 由 Python client 自动下载，来源为 GitHub Releases
- 如需审计，可检查下载 URL 格式：
  `https://github.com/weaviate/weaviate/releases/download/v{version}/weaviate-v{version}-linux-amd64.tar.gz`

---

## 9. 代码结构参考

### 9.1 新增/修改文件清单

| 文件 | 状态 | 职责 |
|---|---|---|
| `infrastructure/vector_store/weaviate_store.py` | 新增 | Weaviate Embedded 向量存储实现 |
| `infrastructure/vector_store/chroma_store.py` | 保留 | ChromaDB 实现（provider=chroma 时使用） |
| `infrastructure/vector_store/memory_store.py` | 保留 | 内存实现（provider=memory 时使用） |
| `core/settings.py` | 修改 | `VectorStoreSettings` 新增 Weaviate 字段 |
| `core/container.py` | 修改 | DI 新增 weaviate 分支 |
| `scripts/migrate_chroma_to_weaviate.py` | 新增 | 数据迁移脚本 |
| `config/settings.yaml` | 修改 | provider 切换 |
| `config/settings.yaml.example` | 修改 | 模板同步 |

### 9.2 WeaviateVectorStore 接口

```python
class WeaviateVectorStore:
    """与 ChromaVectorStore 鸭子类型兼容"""

    collection_name: str                    # Redis 缓存 key 使用

    def upsert(records: list[ChunkRecord]) -> None
    def query(query_vector: list[float], top_k: int) -> list[RetrievalResult]
    def delete_by_document(document_id: str) -> int
    def close() -> None                     # 关闭 Embedded 子进程
```

### 9.3 数据模型映射

```
ChunkRecord (领域模型)           Weaviate Object
─────────────────────           ──────────────────
id: str                  ──▶    uuid: UUID v5(id)
text: str                ──▶    property "text"
dense_vector: list[float] ──▶   vector: [float]
metadata.document_id      ──▶   property "document_id"
metadata.chunk_index      ──▶   property "chunk_index"
metadata (其他)           ──✗   不存入 Weaviate（仅在 chunks.json 中）

RetrievalResult (返回)          Weaviate Query Response
───────────────────────         ───────────────────────
chunk_id                 ◀──    obj.uuid (str)
score                    ◀──    1.0 - obj.metadata.distance
text                     ◀──    obj.properties["text"]
metadata                 ◀──    {document_id, chunk_index}
```

---

## 10. 版本升级

### 10.1 升级 Weaviate 版本

```yaml
# config/settings.yaml
vector_store:
  weaviate_version: "1.38.0"   # 改为新版本号
```

**注意事项：**

- 新版本 binary 会在下次启动时自动下载
- 数据格式通常向后兼容，但建议先备份
- 如果遇到兼容问题，改回旧版本号即可回退

### 10.2 升级 Python Client

```bash
pip install --upgrade weaviate-client
```

- Python client v4 API 与 Weaviate server 1.23.7+ 兼容
- 升级后建议跑一遍测试确认接口无变化

---

## 11. 故障恢复清单

```
□ 1. 检查 Weaviate 进程: ps aux | grep weaviate
□ 2. 检查端口占用: ss -tlnp | grep 8079
□ 3. 检查数据目录: ls -la data/vector_store/weaviate/
□ 4. 检查磁盘空间: df -h
□ 5. 检查应用日志: grep -i error data/traces/traces.jsonl
□ 6. 清理残留进程: pkill -f weaviate-embedded
□ 7. 尝试重启应用
□ 8. 如果数据损坏: 从备份恢复 或 从源文档重建
□ 9. 如果 binary 损坏: rm ~/.cache/weaviate-embedded/weaviate && 重启
```
