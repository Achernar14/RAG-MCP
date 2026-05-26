# Redis 接入方案

## 1. 背景与目标

### 1.1 当前痛点

RAG-MCP 系统在本地运行场景下存在以下性能瓶颈：

- **重复 embedding 计算**: 同一文档的重复请求会反复调用 embedding API
- **无查询缓存**: 相似的用户查询每次都重新进行向量化、检索、生成
- **无会话状态**: 多轮对话无法复用历史检索结果
- **无速率限制保护**: API 调用缺乏流量控制，易触发 provider 限流

### 1.2 接入 Redis 的收益

| 能力 | 收益 | 优先级 |
|------|------|--------|
| Embedding 结果缓存 | 减少重复 API 调用，降低成本 | P0 |
| 检索结果缓存 | 加速相似查询响应 | P0 |
| 会话上下文存储 | 支持多轮对话上下文复用 | P1 |
| 分布式锁 | 防止重复索引构建 | P1 |
| 速率限制 | 保护 API 配额 | P2 |

---

## 2. 架构设计

### 2.1 Redis 数据结构规划

```
REDIS KEYS STRUCTURE
├── rag:embedding:{text_hash}           # String: Embedding 向量缓存
├── rag:retrieval:{query_hash}         # Hash: 检索结果缓存
├── rag:session:{session_id}           # Hash: 会话上下文
├── rag:lock:ingest:{doc_id}           # String: 文档摄取锁
└── rag:ratelimit:{api_key}            # String: API 调用计数
```

**详细结构说明：**

```python
# 1. Embedding 缓存 (TTL: 7天)
Key: rag:embedding:{hash(text)}
Value: {"vector": [0.1, 0.2, ...], "model": "embedding-3", "created_at": "..."}

# 2. 检索结果缓存 (TTL: 1小时)
Key: rag:retrieval:{hash(query)}
Value: {
    "results": [...],
    "query": "原始查询",
    "collection": "rag_mcp_live",
    "timestamp": "..."
}

# 3. 会话存储 (TTL: 24小时)
Key: rag:session:{session_id}
Fields: {
    "messages": "[{role, content, ...}]",
    "last_query": "...",
    "context_docs": "[doc_id1, doc_id2, ...]"
}

# 4. 分布式锁 (TTL: 30分钟)
Key: rag:lock:ingest:{doc_id}
Value: "{worker_id, acquired_at}"

# 5. 速率限制 (TTL: 滑动窗口)
Key: rag:ratelimit:{api_key}:{endpoint}
Value: "{count, window_start}"
```

### 2.2 系统集成点

```
                    ┌─────────────────┐
                    │   FastAPI App   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│ Embedding     │   │ Retrieval     │   │ Session       │
│ Service       │   │ Service       │   │ Manager       │
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
                    ┌───────▼───────┐
                    │ Redis Client  │
                    │ (aioredis)    │
                    └───────┬───────┘
                            │
                    ┌───────▼───────┐
                    │ Redis Server  │
                    │ (local/cloud) │
                    └───────────────┘
```

---

## 3. 配置设计

### 3.1 配置文件扩展 (config/settings.yaml.example)

```yaml
# 新增 Redis 配置节
redis:
  enabled: true
  mode: "standalone"  # standalone | sentinel | cluster

  # 单机模式
  host: "127.00.0.1"
  port: 6379
  db: 0

  # 哨兵模式 (mode=sentinel 时生效)
  sentinel_master: "mymaster"
  sentinel_nodes:
    - host: "127.0.0.1"
      port: 26379

  # 集群模式 (mode=cluster 时生效)
  cluster_nodes:
    - host: "127.0.0.1"
      port: 7001

  # 认证
  password: null  # 通过环境变量 REDIS_PASSWORD 注入
  username: null

  # 连接池
  max_connections: 50
  socket_timeout: 5
  socket_connect_timeout: 5
  retry_on_timeout: true

  # Key 过期时间 (秒)
  ttl:
    embedding: 604800      # 7天
    retrieval: 3600        # 1小时
    session: 86400         # 24小时
    lock: 1800             # 30分钟

  # 缓存策略
  cache:
    embedding_enabled: true
    retrieval_enabled: true
    max_cache_size_mb: 512
```

### 3.2 环境变量 (.env.example)

```bash
# Redis 配置
REDIS_ENABLED=true
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

---

## 4. 实现计划

### 4.1 依赖安装

```toml
# backend/pyproject.toml
[project.optional-dependencies]
redis = [
    "redis>=5.0.0",
    "hiredis>=2.0.0",  # C parser 加速
]
```

安装命令：
```bash
pip install -e ./backend[redis]
```

### 4.2 目录结构

```
backend/src/rag_mcp/infrastructure/
├── redis/
│   ├── __init__.py
│   ├── client.py          # Redis 客户端封装
│   ├── cache.py           # 缓存抽象层
│   ├── lock.py            # 分布式锁
│   └── session.py         # 会话存储
```

### 4.3 核心代码骨架

#### redis/client.py

```python
from typing import Optional
from redis.asyncio import Redis, ConnectionPool
from rag_mcp.core.config import settings

class RedisClient:
    """Redis 客户端单例"""

    _pool: Optional[ConnectionPool] = None
    _client: Optional[Redis] = None

    @classmethod
    async def get_client(cls) -> Redis:
        if cls._client is None:
            cls._pool = ConnectionPool.from_url(
                f"redis://:{settings.redis.password}@"
                f"{settings.redis.host}:{settings.redis.port}"
                f"/{settings.redis.db}",
                max_connections=settings.redis.max_connections,
            )
            cls._client = Redis(connection_pool=cls._pool)
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.close()
```

#### redis/cache.py

```python
from typing import Optional, Any
import hashlib
import json
from .client import RedisClient

class CacheService:
    """统一缓存服务"""

    @staticmethod
    def _hash_key(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    async def get_embedding(self, text: str) -> Optional[list[float]]:
        """获取缓存的 embedding"""
        client = await RedisClient.get_client()
        key = f"rag:embedding:{self._hash_key(text)}"
        data = await client.get(key)
        return json.loads(data)["vector"] if data else None

    async def set_embedding(self, text: str, vector: list[float], ttl: int = 604800):
        """缓存 embedding"""
        client = await RedisClient.get_client()
        key = f"rag:embedding:{self._hash_key(text)}"
        value = json.dumps({"vector": vector, "model": "embedding-3"})
        await client.setex(key, ttl, value)

    async def get_retrieval(self, query: str, collection: str) -> Optional[dict]:
        """获取缓存的检索结果"""
        client = await RedisClient.get_client()
        key = f"rag:retrieval:{collection}:{self._hash_key(query)}"
        return await client.get(key)

    async def set_retrieval(self, query: str, collection: str, results: list, ttl: int = 3600):
        """缓存检索结果"""
        client = await RedisClient.get_client()
        key = f"rag:retrieval:{collection}:{self._hash_key(query)}"
        value = json.dumps({"results": results, "query": query})
        await client.setex(key, ttl, value)
```

### 4.4 服务层集成

```python
# infrastructure/embedding/service.py (修改)
from ..redis.cache import CacheService

class EmbeddingService:
    def __init__(self, cache: CacheService):
        self.cache = cache

    async def embed(self, text: str) -> list[float]:
        # 1. 尝试从缓存获取
        cached = await self.cache.get_embedding(text)
        if cached:
            return cached

        # 2. 调用 API
        vector = await self._call_provider_api(text)

        # 3. 写入缓存
        await self.cache.set_embedding(text, vector)

        return vector
```

---

## 5. 部署方案

### 5.1 本地开发

使用 Docker 快速启动 Redis：

```bash
docker run -d \
  --name rag-redis \
  -p 6379:6379 \
  -v redis-data:/data \
  redis:7-alpine \
  redis-server --appendonly yes
```

### 5.2 生产环境

**推荐方案 1: 云托管服务**
- AWS ElastiCache
- Azure Cache for Redis
- 阿里云 Redis

**推荐方案 2: 自建哨兵模式**

```yaml
# config/settings.yaml.production
redis:
  mode: "sentinel"
  sentinel_master: "rag-master"
  sentinel_nodes:
    - {host: "redis-1.internal", port: 26379}
    - {host: "redis-2.internal", port: 26379}
    - {host: "redis-3.internal", port: 26379}
```

---

## 6. 迁移策略

### 6.1 兼容性设计

Redis 作为可选组件，不影响现有功能：

```python
# pipeline.py
async def create_embedding_service():
    if settings.redis.enabled:
        cache = CacheService()
    else:
        cache = NoOpCache()  # 空操作缓存
    return EmbeddingService(cache=cache)
```

### 6.2 灰度上线

1. **Phase 1**: 仅启用 embedding 缓存，观察命中率
2. **Phase 2**: 启用检索结果缓存
3. **Phase 3**: 启用会话存储和分布式锁

### 6.3 监控指标

```python
# 新增 observability 指标
redis_cache_hit_rate = Gauge("rag:redis:cache_hit_rate")
redis_cache_latency = Histogram("rag:redis:cache_latency_seconds")
redis_connection_errors = Counter("rag:redis:connection_errors")
```

---

## 7. 代码示例

### 7.1 启用 Redis 的完整流程

```bash
# 1. 安装依赖
pip install -e ./backend[redis]

# 2. 启动 Redis
docker run -d --name rag-redis -p 6379:6379 redis:7-alpine

# 3. 配置文件
# config/settings.yaml:
#   redis.enabled: true

# 4. 启动服务
PYTHONPATH=backend/src uvicorn rag_mcp.main:app --reload
```

### 7.2 验证缓存生效

```python
import redis

r = redis.Redis(host='127.0.0.1', port=6379, db=0)

# 查看 embedding 缓存
print(r.keys("rag:embedding:*"))

# 查看缓存内容
key = r.keys("rag:embedding:*")[0]
print(r.get(key))
```

---

## 8. 总结

| 项目 | 内容 |
|------|------|
| 优先级 | P0 (embedding 检索缓存) |
| 工作量 | 预计 3-5 天 |
| 风险 | 低 (可选功能，不影响现有逻辑) |
| 收益 | API 成本降低 30-50%，查询响应提速 2-5x |

**下一步行动**: 优先实现 embedding 缓存和检索结果缓存，验证后再扩展其他能力。
