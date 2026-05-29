# ChromaDB → Weaviate 迁移计划（Embedded 本地部署）

## 1. 迁移目标

将 RAG-MCP 的向量存储后端从 ChromaDB（嵌入式 SQLite）替换为 **Weaviate Embedded**（进程内嵌入，零外部依赖），保持上层检索接口不变。

### 1.1 为什么迁移

| 维度 | ChromaDB | Weaviate Embedded |
|---|---|---|
| 架构 | 嵌入式，SQLite 文件 | 嵌入式，应用进程内启动，数据持久化到磁盘 |
| 并发 | SQLite 锁冲突需 retry 逻辑 | 无 SQLite 锁，原生并发安全 |
| 过滤 | 基础 dict where | 类型化 Filter，支持范围/嵌套 |
| 批量写入 | `add()` 传列表 | `batch.fixed_size()` / `batch.stream()` |
| 网络要求 | 无 | 无（进程内通信，127.0.0.1 回环） |
| 运维 | 零运维 | 零运维（与 ChromaDB 同级别） |

### 1.2 部署模式选择

```
┌──────────────────────────────────────────────────────────────────────────┐
│                 三种 Weaviate 部署模式对比                                │
├────────────────┬──────────────┬──────────────┬──────────────────────────┤
│                │ Docker       │ Embedded     │ Weaviate Cloud           │
├────────────────┼──────────────┼──────────────┼──────────────────────────┤
│ 启动方式       │ docker compose│ Python 自动   │ SaaS 服务                │
│                │              │ 下载+启动     │                          │
│ 客户机网络要求 │ 需 ping 通    │ 无（进程内）  │ 需公网访问               │
│                │ Docker 容器  │              │                          │
│ 数据持久化     │ Docker Volume│ 本地目录      │ 云端托管                 │
│ 适用场景       │ 团队开发     │ ✅ 本地部署   │ 生产环境                 │
│                │              │   单机使用    │                          │
│ 额外依赖       │ Docker       │ 无           │ 付费                     │
│ 本项目选择     │ ✗ 不选       │ ✓ 选择        │ ✗ 不选                   │
└────────────────┴──────────────┴──────────────┴──────────────────────────┘
```

**选择 Embedded 的理由：**

1. **零网络依赖**：Weaviate 由 Python 客户端在应用进程内自动启动，通信走 127.0.0.1 回环地址，无需客户机能 ping 通任何外部服务或 Docker 容器
2. **与 ChromaDB 同级体验**：`pip install` 即用，无需预装 Docker 或手动启停服务
3. **数据持久化**：首次运行自动创建数据目录，进程退出后数据保留，下次启动自动复用
4. **自动下载二进制**：首次运行时自动下载 Weaviate server binary 到 `~/.cache/weaviate-embedded/`，后续复用

### 1.3 迁移原则

- **接口不变**：`VectorStoreRepository` 的三个方法签名保持不变
- **配置驱动**：通过 `settings.yaml` 切换 `provider: weaviate`，不改动业务层
- **平滑共存**：`chroma` / `weaviate` / `memory` 三种 provider 共存，按配置选择
- **零外部依赖**：不依赖 Docker、不依赖外部网络，`pip install` 后即用

---

## 2. Weaviate Embedded 工作原理

### 2.1 生命周期

```
应用启动
  │
  ▼ weaviate.connect_to_embedded() 或 WeaviateClient(embedded_options=...)
  │
  ├── 首次运行？
  │   ├── Yes → 下载 Weaviate binary → ~/.cache/weaviate-embedded/weaviate
  │   └── No  → 复用已下载的 binary
  │
  ├── 启动 Weaviate 子进程（绑定 127.0.0.1:8079）
  │
  ├── 检查数据目录
  │   ├── persistence_data_path 已有数据？ → 复用
  │   └── 空目录？ → 新建
  │
  └── 返回 client 对象，正常使用

应用退出 / client.close()
  │
  ▼ Weaviate 子进程自动退出
      数据目录持久保留在磁盘上
```

### 2.2 关键配置参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `persistence_data_path` | `~/.local/share/weaviate` | 数据存储目录（可自定义到项目内） |
| `binary_path` | `~/.cache/weaviate-embedded` | 二进制缓存目录 |
| `hostname` | `127.0.0.1` | 绑定地址（仅本地回环） |
| `port` | `8079` | REST 端口（注意：不是 8080） |
| `version` | 最新稳定版 | Weaviate server 版本 |

---

## 3. 影响范围分析

### 3.1 文件变更矩阵

```
类型标记：  ✏️ 修改  🆕 新建
```

| 文件 | 类型 | 说明 |
|---|---|---|
| `backend/pyproject.toml` | ✏️ | 新增 `weaviate-client` 依赖 |
| `backend/src/rag_mcp/core/settings.py` | ✏️ | 扩展 `VectorStoreSettings`，新增 Weaviate Embedded 配置 |
| `backend/src/rag_mcp/core/container.py` | ✏️ | 移除 Chroma 专属 import，新增 Weaviate 分支 |
| `backend/src/rag_mcp/infrastructure/vector_store/weaviate_store.py` | 🆕 | Weaviate 向量存储实现（核心新文件） |
| `backend/src/rag_mcp/infrastructure/vector_store/chroma_store.py` | 保留 | 作为备选 provider 不删除 |
| `config/settings.yaml` | ✏️ | provider 改为 `weaviate`，新增 embedded 参数 |
| `config/settings.yaml.example` | ✏️ | 同步更新模板 |
| `scripts/migrate_chroma_to_weaviate.py` | 🆕 | 数据迁移脚本 |
| 10 个测试文件 | ✏️ | fixture 中 `provider` 改为 `"weaviate"` |

### 3.2 不需要改动的文件（接口隔离）

以下文件仅通过鸭子类型接口调用 `upsert / query / delete_by_document`，**无需任何修改**：

```
domain/repositories/contracts.py         ← 抽象接口定义
domain/services/retrieval.py             ← 调用 vector_store.query()
domain/services/hybrid_retrieval.py      ← 调用 vector_store.query() + 读取 collection_name
infrastructure/pipeline.py               ← 调用 vector_store.upsert() / delete_by_document()
application/use_cases/delete_document.py ← 调用 vector_store.delete_by_document()
application/use_cases/list_collections.py
application/use_cases/get_knowledge_status.py
application/use_cases/rebuild_collection.py
application/dto/models.py                ← 仅暴露 vector_store_provider: str
```

---

## 4. 详细实施步骤

### Phase 0：环境准备

#### 0.1 更新依赖

**`backend/pyproject.toml`**：

```diff
 dependencies = [
-    "chromadb>=1.5.0",
+    "chromadb>=1.5.0",
+    "weaviate-client>=4.20.0",
     "fastapi>=0.115.0",
```

> `chromadb` 暂时保留，作为可切换的备选 provider。后续可完全移除。

安装：

```bash
cd backend && pip install -e ".[dev]"
```

**首次安装后无需额外操作** — Weaviate binary 会在代码首次运行时自动下载。

#### 0.2 前置条件

| 条件 | 状态 |
|---|---|
| Python ≥ 3.11 | 项目已要求 |
| Linux 操作系统 | Weaviate Embedded 支持 Linux 和 macOS |
| 网络访问（仅首次） | 需下载 ~100MB Weaviate binary；后续离线可用 |
| Docker | **不需要** |

---

### Phase 1：配置层改造

#### 1.1 扩展 `VectorStoreSettings`

**文件**：`backend/src/rag_mcp/core/settings.py`（lines 69-72）

```python
class VectorStoreSettings(BaseModel):
    provider: str = "weaviate"                          # 改默认值
    persist_path: str = "data/vector_store/chroma_live" # chroma 备用
    collection_name: str = "RAG_MCP"                    # Weaviate collection（首字母大写）

    # --- Weaviate Embedded 配置 ---
    weaviate_persistence_data_path: str = "data/vector_store/weaviate"  # 数据目录
    weaviate_version: str = "1.37.2"                    # server binary 版本
    weaviate_hostname: str = "127.0.0.1"                # 绑定地址
    weaviate_port: int = 8079                           # Embedded 默认端口
```

> **注意**：Embedded 模式不需要 `grpc_port`（内部自动处理）、不需要 `api_key_env`（本地匿名访问），配置项大幅精简。

#### 1.2 更新配置文件

**`config/settings.yaml`**（lines 33-36 改为）：

```yaml
vector_store:
  provider: "weaviate"
  collection_name: "RAG_MCP"
  persist_path: "data/vector_store/chroma_live"            # chroma 备用时仍需要
  weaviate_persistence_data_path: "data/vector_store/weaviate"  # 数据持久化目录
  weaviate_version: "1.37.2"
  weaviate_hostname: "127.0.0.1"
  weaviate_port: 8079
```

**`config/settings.yaml.example`** 同步更新。

> 不需要修改 `.env.example` — Embedded 模式无需 API Key。

---

### Phase 2：核心实现 — `WeaviateVectorStore`

#### 2.1 新建文件

**文件**：`backend/src/rag_mcp/infrastructure/vector_store/weaviate_store.py`

```python
"""Weaviate Embedded vector store implementation.

Uses Weaviate's embedded mode to run the server in-process.
No Docker, no external service — just like ChromaDB's PersistentClient.
"""

from __future__ import annotations

from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.classes.query import Filter, MetadataQuery
from weaviate.embedded import EmbeddedOptions

from rag_mcp.core.exceptions import ProviderError
from rag_mcp.domain.entities.models import ChunkRecord, RetrievalResult


class WeaviateVectorStore:
    """Persist embeddings and metadata in Weaviate Embedded."""

    _SCHEMA = [
        Property(name="text", data_type=DataType.TEXT),
        Property(name="document_id", data_type=DataType.TEXT),
        Property(name="chunk_index", data_type=DataType.INT),
    ]

    def __init__(
        self,
        *,
        persistence_data_path: str,
        version: str = "1.37.2",
        hostname: str = "127.0.0.1",
        port: int = 8079,
        collection_name: str = "RAG_MCP",
    ) -> None:
        self.collection_name = collection_name

        data_dir = Path(persistence_data_path)
        data_dir.mkdir(parents=True, exist_ok=True)

        embedded_opts = EmbeddedOptions(
            persistence_data_path=str(data_dir),
            version=version,
            hostname=hostname,
            port=port,
            additional_env_vars={"LOG_LEVEL": "error"},
        )

        try:
            self.client = weaviate.WeaviateClient(
                embedded_options=embedded_opts,
            )
            self.client.connect()
        except Exception as exc:
            raise ProviderError(f"Weaviate Embedded 启动失败: {exc}") from exc

        self._ensure_collection()

    # ------------------------------------------------------------------
    # Public interface (duck-typed with ChromaVectorStore)
    # ------------------------------------------------------------------

    def upsert(self, records: list[ChunkRecord]) -> None:
        """Insert or replace records."""
        if not records:
            return
        collection = self.client.collections.use(self.collection_name)
        with collection.batch.fixed_size(batch_size=200) as batch:
            for record in records:
                batch.add_object(
                    properties={
                        "text": record.text,
                        "document_id": record.metadata.get("document_id", ""),
                        "chunk_index": record.metadata.get("chunk_index", 0),
                    },
                    vector=record.dense_vector,
                    uuid=self._record_uuid(record.id),
                )
        if collection.batch.failed_objects:
            failed = collection.batch.failed_objects
            raise ProviderError(
                f"Weaviate batch upsert: {len(failed)} failures, "
                f"first: {failed[0].message}"
            )

    def query(self, query_vector: list[float], top_k: int) -> list[RetrievalResult]:
        """Run nearest-neighbor search."""
        collection = self.client.collections.use(self.collection_name)
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=top_k,
            return_metadata=MetadataQuery(distance=True),
        )
        results: list[RetrievalResult] = []
        for obj in response.objects:
            results.append(RetrievalResult(
                chunk_id=str(obj.uuid),
                score=self._distance_to_score(obj.metadata.distance),
                text=obj.properties.get("text", ""),
                metadata={
                    "document_id": obj.properties.get("document_id", ""),
                    "chunk_index": obj.properties.get("chunk_index", 0),
                },
            ))
        return results

    def delete_by_document(self, document_id: str) -> int:
        """Delete all chunks belonging to a document."""
        collection = self.client.collections.use(self.collection_name)
        result = collection.data.delete_many(
            where=Filter.by_property("document_id").equal(document_id),
        )
        return result.successful

    def close(self) -> None:
        """Shut down the embedded Weaviate instance."""
        self.client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        """Create the collection if it does not exist."""
        if not self.client.collections.exists(self.collection_name):
            self.client.collections.create(
                name=self.collection_name,
                vector_config=Configure.Vectors.self_provided(
                    vector_index_config=Configure.VectorIndex.hnsw(
                        distance_metric=VectorDistances.COSINE,
                    ),
                ),
                properties=self._SCHEMA,
            )

    @staticmethod
    def _record_uuid(chunk_id: str) -> str:
        """Deterministic UUID v5 from chunk ID for upsert semantics."""
        return str(uuid5(NAMESPACE_DNS, chunk_id))

    @staticmethod
    def _distance_to_score(distance: float | None) -> float:
        """Convert cosine distance to a descending similarity score."""
        if distance is None:
            return 0.0
        return 1.0 - distance  # cosine distance → similarity
```

#### 2.2 与 ChromaDB 的对比

```
┌────────────────────────────────────────────────────────────────────────┐
│  ChromaDB PersistentClient          vs    Weaviate Embedded           │
├──────────────────────────────────────┼─────────────────────────────────┤
│                                      │                                 │
│  chromadb.PersistentClient(          │  weaviate.WeaviateClient(       │
│      path="./data/chroma"            │      embedded_options=          │
│  )                                   │        EmbeddedOptions(         │
│                                      │          persistence_data_path= │
│  · 首次运行：创建 SQLite 文件         │            "./data/weaviate",   │
│  · 数据存磁盘，进程退出后保留         │          version="1.37.2",      │
│  · 零外部依赖                        │        )                        │
│  · 无需 Docker                       │  )                              │
│  · 绑定 127.0.0.1                    │  client.connect()               │
│                                      │                                 │
│                                      │  · 首次运行：下载 binary + 创建 │
│                                      │    数据目录                     │
│                                      │  · 数据存磁盘，进程退出后保留   │
│                                      │  · 零外部依赖（首次需网络下载） │
│                                      │  · 无需 Docker                  │
│                                      │  · 绑定 127.0.0.1              │
│                                      │  · 子进程随应用退出自动关闭     │
└──────────────────────────────────────┴─────────────────────────────────┘
```

#### 2.3 关键设计决策

| 决策点 | 方案 | 理由 |
|---|---|---|
| **部署模式** | Embedded（`WeaviateClient + EmbeddedOptions`） | 无需 Docker，与 ChromaDB 同级零运维体验 |
| **连接方式** | `WeaviateClient(embedded_options=...)` + `.connect()` | 官方推荐方式，可传完整配置 |
| **数据目录** | `data/vector_store/weaviate`（项目内） | 与 ChromaDB 的 `data/vector_store/chroma_live` 平行，方便管理 |
| **Binary 缓存** | 默认 `~/.cache/weaviate-embedded/` | 不自定义，避免影响其他项目 |
| **端口** | `8079`（Embedded 默认） | 与 ChromaDB 无冲突，无需手动管理端口 |
| **日志级别** | `LOG_LEVEL=error` | 减少 Embedded server 的日志噪音 |
| **距离转换** | `1.0 - distance` | Weaviate 返回余弦距离（0=完全相同），直接转相似度 |
| **Upsert 语义** | UUID v5 确定性生成 | 同一 chunk 生成相同 UUID，重复 insert 即覆盖 |
| **Batch 写入** | `fixed_size(200)` | Weaviate 推荐批量大小 |

---

### Phase 3：DI 容器改造

#### 3.1 修改 `container.py`

**文件**：`backend/src/rag_mcp/core/container.py`

**改动 1 — 移除 Chroma 专属 import（line 8）：**

```diff
-from chromadb.api import shared_system_client
```

**改动 2 — 新增 Weaviate import（在 line 52 附近）：**

```python
from rag_mcp.infrastructure.vector_store.weaviate_store import WeaviateVectorStore
```

**改动 3 — `_create_vector_store()` 新增 weaviate 分支（lines 251-262）：**

```python
def _create_vector_store(self):
    provider = self.settings.vector_store.provider.lower()
    if provider == "memory":
        return InMemoryVectorStore()
    if provider == "chroma":
        return ChromaVectorStore(
            persist_path=str(
                resolve_project_path(self.settings.vector_store.persist_path)
            ),
            collection_name=self.settings.vector_store.collection_name,
        )
    if provider == "weaviate":
        return WeaviateVectorStore(
            persistence_data_path=str(
                resolve_project_path(
                    self.settings.vector_store.weaviate_persistence_data_path
                )
            ),
            version=self.settings.vector_store.weaviate_version,
            hostname=self.settings.vector_store.weaviate_hostname,
            port=self.settings.vector_store.weaviate_port,
            collection_name=self.settings.vector_store.collection_name,
        )
    raise ValueError(f"Unsupported vector store provider: {provider}")
```

**改动 4 — `close()` 移除 Chroma 缓存清理（lines 205-214）：**

```python
def close(self) -> None:
    """Release resources held by the container."""
    close_method = getattr(self.vector_store, "close", None)
    if callable(close_method):
        close_method()
    if self._redis_client is not None:
        self._redis_client.close()
```

> Weaviate Embedded 的 `client.close()` 会自动关闭子进程，无需额外清理。

---

### Phase 4：数据迁移脚本

**新建**：`scripts/migrate_chroma_to_weaviate.py`

```python
#!/usr/bin/env python3
"""One-time migration: ChromaDB → Weaviate Embedded.

Usage:
    cd backend
    python scripts/migrate_chroma_to_weaviate.py \
        --chroma-path ../data/vector_store/chroma_live \
        --chroma-collection rag_mcp_live \
        --weaviate-data-path ../data/vector_store/weaviate \
        --weaviate-collection RAG_MCP
"""

import argparse
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import chromadb
import weaviate
from weaviate.classes.config import Configure, DataType, Property, VectorDistances
from weaviate.embedded import EmbeddedOptions


def migrate(args):
    # --- 源：ChromaDB ---
    chroma = chromadb.PersistentClient(path=args.chroma_path)
    src = chroma.get_or_create_collection(args.chroma_collection)
    all_ids = src.get(include=[])["ids"]
    if not all_ids:
        print("ChromaDB collection 为空，无需迁移。")
        return

    print(f"ChromaDB 中发现 {len(all_ids)} 条记录")

    batch_size = 200
    records = []
    for i in range(0, len(all_ids), batch_size):
        batch_ids = all_ids[i : i + batch_size]
        result = src.get(
            ids=batch_ids,
            include=["documents", "embeddings", "metadatas"],
        )
        for j in range(len(result["ids"])):
            records.append({
                "id": result["ids"][j],
                "text": result["documents"][j],
                "vector": result["embeddings"][j],
                "metadata": result["metadatas"][j],
            })

    # --- 目标：Weaviate Embedded ---
    data_dir = Path(args.weaviate_data_path)
    data_dir.mkdir(parents=True, exist_ok=True)

    client = weaviate.WeaviateClient(
        embedded_options=EmbeddedOptions(
            persistence_data_path=str(data_dir),
            version="1.37.2",
            hostname="127.0.0.1",
            port=8079,
            additional_env_vars={"LOG_LEVEL": "error"},
        ),
    )
    client.connect()

    if not client.collections.exists(args.weaviate_collection):
        client.collections.create(
            name=args.weaviate_collection,
            vector_config=Configure.Vectors.self_provided(
                vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE,
                ),
            ),
            properties=[
                Property(name="text", data_type=DataType.TEXT),
                Property(name="document_id", data_type=DataType.TEXT),
                Property(name="chunk_index", data_type=DataType.INT),
            ],
        )

    collection = client.collections.use(args.weaviate_collection)

    with collection.batch.fixed_size(batch_size=200) as batch:
        for rec in records:
            meta = rec["metadata"] or {}
            batch.add_object(
                properties={
                    "text": rec["text"] or "",
                    "document_id": meta.get("document_id", ""),
                    "chunk_index": int(meta.get("chunk_index", 0)),
                },
                vector=rec["vector"],
                uuid=str(uuid5(NAMESPACE_DNS, rec["id"])),
            )

    failed = collection.batch.failed_objects
    if failed:
        print(f"WARNING: {len(failed)} 条记录写入失败")
        for f in failed[:5]:
            print(f"  - {f.message}")
    else:
        print(f"成功迁移 {len(records)} 条记录到 Weaviate")

    client.close()
    chroma.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chroma-path", required=True)
    parser.add_argument("--chroma-collection", default="rag_mcp_live")
    parser.add_argument("--weaviate-data-path", required=True)
    parser.add_argument("--weaviate-collection", default="RAG_MCP")
    migrate(parser.parse_args())
```

---

### Phase 5：测试适配

#### 5.1 测试 Fixture 更新

10 个测试文件中 `"provider": "chroma"` 需改为 `"weaviate"`，并替换连接参数：

```python
# 改前（ChromaDB）
"vector_store": {
    "provider": "chroma",
    "persist_path": "data/vector_store/chroma_test",
    "collection_name": "test_collection",
}

# 改后（Weaviate Embedded）
"vector_store": {
    "provider": "weaviate",
    "collection_name": "TestCollection",
    "weaviate_persistence_data_path": "data/vector_store/weaviate_test",
    "weaviate_version": "1.37.2",
    "weaviate_hostname": "127.0.0.1",
    "weaviate_port": 8079,
}
```

> 测试中每个 fixture 使用独立的 `weaviate_persistence_data_path`，避免数据互相污染。测试结束后 Weaviate 子进程随 `container.close()` 自动退出。

#### 5.2 需要改动的测试文件清单

| 文件 | 改动 |
|---|---|
| `tests/unit/test_mvp_flow.py:20` | provider + 替换为 weaviate embedded 参数 |
| `tests/unit/test_hybrid_retrieval.py:20` | 同上 |
| `tests/unit/test_management_flows.py:22` | 同上 |
| `tests/unit/test_mcp_protocol.py:19` | 同上 |
| `tests/unit/test_evaluation_flows.py:46` | 同上 |
| `tests/unit/test_dashboard_service.py:19` | 同上 |
| `tests/unit/test_answer_generation.py:46` | 同上 |
| `tests/unit/test_trace_management.py:21` | 同上 |
| `tests/unit/test_mcp_sdk_server.py:20` | 同上 |
| `tests/unit/test_mcp_stdio_server.py:23` | 同上 |
| `tests/unit/test_prompt_and_provider_infra.py` | memory 模式不变，persist_path 可删 |

#### 5.3 CI 环境

CI 中无需启动 Docker service container。Embedded 模式由 Python 进程自动管理：

```yaml
# GitHub Actions — 无需 services 块
steps:
  - uses: actions/checkout@v4
  - uses: actions/setup-python@v5
    with:
      python-version: "3.11"
  - run: pip install -e ".[dev]"
  - run: pytest
    # Weaviate Embedded 自动在测试进程中启动
```

---

### Phase 6：文档更新

| 文件 | 改动 |
|---|---|
| `README.md` | ChromaDB → Weaviate Embedded 安装说明 |
| `docs/embedding-structure.md` | 更新 Vector Store 章节 |
| `docs/技术文档.md` | 同步更新 |

---

## 5. ChromaDB vs Weaviate API 映射

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    API 对照表                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  连接 / 启动                                                             │
│  ──────────                                                              │
│  Chroma:  chromadb.PersistentClient(path="./data")                      │
│  Weaviate: weaviate.WeaviateClient(                                     │
│              embedded_options=EmbeddedOptions(                           │
│                persistence_data_path="./data/weaviate",                  │
│                version="1.37.2"))                                        │
│            client.connect()                                             │
│                                                                         │
│  创建 Collection                                                         │
│  ──────────────                                                         │
│  Chroma:  client.get_or_create_collection("name")                       │
│  Weaviate: client.collections.create(                                   │
│              name="Name",                                               │
│              vector_config=Configure.Vectors.self_provided(             │
│                vector_index_config=Configure.VectorIndex.hnsw(          │
│                  distance_metric=VectorDistances.COSINE))               │
│            )                                                             │
│                                                                         │
│  插入 / Upsert                                                           │
│  ─────────────                                                           │
│  Chroma:  collection.upsert(                                            │
│              ids=[...], documents=[...],                                 │
│              embeddings=[...], metadatas=[...])                          │
│  Weaviate: with collection.batch.fixed_size(200) as batch:              │
│              batch.add_object(properties={...}, vector=[...], uuid=...)  │
│                                                                         │
│  查询                                                                    │
│  ────                                                                    │
│  Chroma:  collection.query(query_embeddings=[vec], n_results=5)         │
│           → {"ids": [[...]], "documents": [[...]],                      │
│              "distances": [[...]]}                                      │
│  Weaviate: collection.query.near_vector(near_vector=vec, limit=5,       │
│              return_metadata=MetadataQuery(distance=True))              │
│           → response.objects[{.uuid, .properties, .metadata.distance}]  │
│                                                                         │
│  按条件删除                                                               │
│  ──────────                                                              │
│  Chroma:  collection.get(where={"document_id": "x"})                    │
│           collection.delete(ids=result["ids"])                          │
│  Weaviate: collection.data.delete_many(                                 │
│              where=Filter.by_property("document_id").equal("x"))        │
│                                                                         │
│  距离 → 分数                                                             │
│  ────────────                                                            │
│  Chroma:  score = 1.0 / (1.0 + max(distance, 0.0))   # L2 距离         │
│  Weaviate: score = 1.0 - distance                     # 余弦距离         │
│                                                                         │
│  关闭                                                                    │
│  ────                                                                    │
│  Chroma:  client.close() + SharedSystemClient.clear_system_cache()      │
│  Weaviate: client.close()  ← 自动关闭子进程                              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 风险与注意事项

### 6.1 Chunk ID 格式变化

- **ChromaDB**：原始字符串 ID，如 `abc123:0`
- **Weaviate**：UUID v5 确定性映射，如 `a1b2c3d4-e5f6-5a7b-...`
- **解决**：`hybrid_retrieval.py` 的 RRF 融合通过 `chunk_id` 去重，UUID 格式不影响匹配正确性（同一 chunk 始终生成同一 UUID）

### 6.2 Metadata 覆盖范围

- **Weaviate property schema 固定**：`text / document_id / chunk_index`
- 详细元信息仍通过 `chunks.json` 查询（当前逻辑已是如此）
- 如需在 Weaviate 中存储更多 property，需在 `_SCHEMA` 中预定义

### 6.3 首次运行网络需求

- 首次调用 `connect_to_embedded()` 需下载 ~100MB Weaviate binary
- 下载后缓存在 `~/.cache/weaviate-embedded/`，后续完全离线
- **离线部署方案**：提前下载 binary 并指定 `binary_path`

```python
EmbeddedOptions(
    binary_path="/opt/weaviate/weaviate",  # 预置 binary 路径
    persistence_data_path="./data/weaviate",
)
```

### 6.4 进程生命周期

- Weaviate 子进程随 Python 应用启动/退出
- 非正常退出（kill -9）可能遗留子进程 — 建议在 `close()` 中加 `atexit` 兜底
- 数据持久化在 `persistence_data_path` 目录中，进程崩溃不丢数据

### 6.5 `collection_name` 属性

`hybrid_retrieval.py:109,133` 通过 `getattr(self.vector_store, "collection_name", "default")` 读取。

→ 已在 `WeaviateVectorStore.__init__` 中设置 `self.collection_name`。

### 6.6 Embedded 模式的 "Experimental" 标记

Weaviate 官方文档标注 Embedded 为 **Experimental**。实际影响评估：

- API 已稳定多个版本（v3.15+ 引入，v4 完整支持）
- 社区大量生产使用案例
- 核心功能（CRUD、向量搜索、批量写入）完整可用
- 风险可控：配置中保留 `provider: chroma` 作为回退

---

## 7. 目录结构对比

```
迁移前                              迁移后
──────                              ──────

data/vector_store/                  data/vector_store/
├── chroma_live/                    ├── chroma_live/              ← 保留，chroma 备用
│   └── chroma.sqlite3              │   └── chroma.sqlite3
├── documents.json                  ├── documents.json
├── chunks.json                     ├── chunks.json
├── bm25_index.json                 ├── bm25_index.json
                                    └── weaviate/                 ← 新增
                                        └── (Weaviate 自动管理)
                                        ├── lsm/
                                        └── segment/

~/.cache/                           ~/.cache/
                                    └── weaviate-embedded/        ← 新增（binary 缓存）
                                        └── weaviate              ~100MB
```

---

## 8. 实施时间线

```
Week 1
├── Day 1:    Phase 0 — pip install weaviate-client + 验证 Embedded 启动
├── Day 2-3:  Phase 1 — 配置层改造（settings, yaml）
└── Day 4-5:  Phase 2 — WeaviateVectorStore 核心实现 + 单元测试

Week 2
├── Day 1-2:  Phase 3 — DI 容器改造 + 集成测试
├── Day 3:    Phase 4 — 数据迁移脚本编写 + 验证
├── Day 4:    Phase 5 — 全量测试适配
└── Day 5:    Phase 6 — 文档更新 + 回归测试
```

---

## 9. 验收标准

- [ ] `pip install weaviate-client` 后无报错
- [ ] `settings.yaml` 中 `provider: weaviate` 时，应用启动自动拉起 Embedded Weaviate
- [ ] ingest 接口正常写入，数据持久化到 `data/vector_store/weaviate/`
- [ ] 应用退出后重启，已有数据可正常检索
- [ ] hybrid retrieval（dense + sparse + RRF + rerank）全链路通过
- [ ] `delete_by_document` 正确清理指定文档的所有 chunk
- [ ] 现有 10 个测试文件全部通过
- [ ] `provider: chroma` 仍可正常切换回使用
- [ ] 迁移脚本可将现有 ChromaDB 数据无损导入 Weaviate
- [ ] **全程无需 Docker，无需客户机访问外部网络**（首次安装除外）

---

## 参考资料

- [Embedded Weaviate 官方文档](https://docs.weaviate.io/deploy/installation-guides/embedded)
- [Weaviate Embedded 连接指南](https://docs.weaviate.io/weaviate/connections/connect-embedded)
- [Weaviate Python v4 Client 文档](https://docs.weaviate.io/weaviate/client-libraries/python)
- [Embedded Weaviate 博客：10 行代码运行向量数据库](https://weaviate.io/blog/embedded-local-weaviate)
