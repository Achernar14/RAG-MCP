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

### 2.1 关键设计决策

1. **同步 API**: 当前项目全部使用同步 Python，使用 `redis.Redis`（非 `redis.asyncio`）
2. **可选组件**: `redis.enabled=false` 时所有缓存操作走 NoOp 透传，不影响现有功能
3. **Wrapper 模式**: 通过 `CachingEmbeddingProvider` 包装器缓存 Embedding 结果，不修改底层 Provider
4. **配置驱动**: 通过 `settings.yaml` 中 `redis.enabled` 控制，零代码切换
5. **优雅降级**: Redis 连接失败时自动回退到无缓存模式

### 2.2 Redis 数据结构规划

```
REDIS KEYS STRUCTURE
├── rag:emb:{sha256(text)}              # String: Embedding 向量缓存 (TTL 7d)
├── rag:ret:{sha256(query|top_k|col)}   # String: 检索结果缓存 (TTL 1h)
├── rag:session:{session_id}            # Hash: 会话上下文 (P1, TTL 24h)
├── rag:lock:ingest:{doc_id}            # String: 文档摄取锁 (P1, TTL 30m)
└── rag:ratelimit:{api_key}:{endpoint}  # String: API 调用计数 (P2)
```

### 2.3 集成架构

```
                     ┌─────────────────┐
                     │ Application     │
                     │ Container       │
                     └────────┬────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
           ▼                  ▼                  ▼
  ┌────────────────┐  ┌───────────────┐  ┌───────────────┐
  │ Caching        │  │ Query         │  │ (P1/P2 扩展)  │
  │ Embedding      │  │ Knowledge     │  │ Session/Lock  │
  │ Provider       │  │ UseCase       │  └───────────────┘
  │ ┌────────────┐ │  │ (retrieval    │
  │ │ Real Prov. │ │  │  cache)       │
  │ └────────────┘ │  └───────┬───────┘
  └───────┬────────┘          │
          │                   │
          └───────────┬───────┘
                      │
              ┌───────▼───────┐
              │ RedisCache    │
              │ Service       │
              └───────┬───────┘
                      │
              ┌───────▼───────┐
              │ Redis Client  │
              │ (sync)        │
              └───────┬───────┘
                      │
              ┌───────▼───────┐
              │ Redis Server  │
              └───────────────┘
```

---

## 3. 配置设计

### 3.1 Settings 模型扩展 (core/settings.py)

```python
class RedisCacheSettings(BaseModel):
    embedding_enabled: bool = False
    retrieval_enabled: bool = False

class RedisSettings(BaseModel):
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 6379
    db: int = 0
    password_env: str | None = None
    max_connections: int = 50
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    ttl_embedding: int = 604800       # 7天
    ttl_retrieval: int = 3600         # 1小时
    cache: RedisCacheSettings = Field(default_factory=RedisCacheSettings)
```

### 3.2 配置文件扩展 (config/settings.yaml)

```yaml
redis:
  enabled: false
  host: "127.0.0.1"
  port: 6379
  db: 0
  password_env: "REDIS_PASSWORD"
  max_connections: 50
  socket_timeout: 5.0
  ttl_embedding: 604800
  ttl_retrieval: 3600
  cache:
    embedding_enabled: true
    retrieval_enabled: true
```

### 3.3 环境变量 (.env.example)

```bash
REDIS_PASSWORD=
```

---

## 4. 实现计划

### 4.1 目录结构

```
backend/src/rag_mcp/infrastructure/
├── redis/
│   ├── __init__.py
│   ├── client.py          # Redis 客户端封装 (sync)
│   └── cache.py           # 缓存服务 (embedding + retrieval)
├── embedding/
│   ├── caching_embedding.py  # CachingEmbeddingProvider (新增)
│   ├── hash_embedding.py     # 现有
│   └── zhipu_embedding.py    # 现有
```

### 4.2 实现步骤

| 步骤 | 内容 | 文件 |
|------|------|------|
| 1 | 添加 redis 依赖 | `pyproject.toml` |
| 2 | 新增 RedisSettings | `core/settings.py` |
| 3 | Redis 客户端封装 | `infrastructure/redis/client.py` |
| 4 | 缓存服务 | `infrastructure/redis/cache.py` |
| 5 | CachingEmbeddingProvider | `infrastructure/embedding/caching_embedding.py` |
| 6 | 容器集成 | `core/container.py` |
| 7 | 检索缓存集成 | `application/use_cases/query_knowledge.py` |
| 8 | 更新配置文件 | `settings.yaml`, `.env.example` |
| 9 | 单元测试 | `tests/unit/test_redis_cache.py` |

---

## 5. 兼容性设计

| 场景 | 行为 |
|------|------|
| `redis.enabled=false` (默认) | 完全跳过 Redis，行为不变 |
| Redis 连接失败 | 自动降级到无缓存模式，记录 warning 日志 |
| 缓存未命中 | 回退到原有 Provider 调用 |
| TTL 过期 | 自动重新计算 |
| `redis` 包未安装 | import 失败时 fallback 到无缓存模式 |

---

## 6. 部署方案

### 6.1 本地开发

```bash
docker run -d \
  --name rag-redis \
  -p 6379:6379 \
  redis:7-alpine \
  redis-server --appendonly yes
```

### 6.2 启用 Redis

```bash
# 1. 安装依赖
pip install -e "./backend[redis]"

# 2. 启动 Redis
docker run -d --name rag-redis -p 6379:6379 redis:7-alpine

# 3. 修改 config/settings.yaml
# redis.enabled: true

# 4. 启动服务
PYTHONPATH=backend/src python -m rag_mcp.mcp.server
```

---

## 7. 总结

| 项目 | 内容 |
|------|------|
| 优先级 | P0 (embedding + retrieval 缓存) |
| 实现方式 | 同步 `redis.Redis` + Wrapper 模式 |
| 工作量 | 预计 1-2 天 |
| 风险 | 低 (可选功能，不影响现有逻辑) |
| 收益 | API 成本降低 30-50%，查询响应提速 2-5x |
| 设计原则 | Wrapper 模式、配置驱动、优雅降级 |
