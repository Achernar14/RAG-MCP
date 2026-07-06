# RAG-MCP 集成指南

本文档说明如何将 RAG-MCP 接入外部 LLM 网关，实现统一的模型访问和成本管控。

---

## 1. 集成架构

RAG-MCP 的 LLM 调用基于 OpenAI 兼容协议。对外部网关而言，RAG-MCP 就是一个标准的 OpenAI API 客户端。

```
┌──────────┐     ┌─────────────────┐     ┌──────────────┐
│ RAG-MCP  │────▶│  LLM Gateway    │────▶│  LLM Backend │
│          │     │  (Synapse/      │     │  (DeepSeek/  │
│          │     │   LiteLLM/...)  │     │   OpenAI/...) │
└──────────┘     └─────────────────┘     └──────────────┘
     │                                             │
     └────────── 直连模式（可选）────────────────┘
```

### 两种模式对比

| | 直连模式 | 网关模式 |
|---|---|---|
| **配置** | `api_base` 直接指向 LLM 供应商 | `api_base` 指向网关地址 |
| **API Key 管理** | 每个供应商各自管理 | 网关统一管理 |
| **成本管控** | 依赖供应商 Dashboard | 网关统一限流/计费 |
| **模型切换** | 修改 `model` + `api_base` | 网关侧路由，客户端无感 |
| **适用场景** | 开发测试、单供应商 | 生产环境、多供应商、团队协作 |

---

## 2. URL 拼接规范

RAG-MCP 的 URL 构造逻辑为：

```
请求 URL = {api_base}/chat/completions
```

其中 `api_base` 会自动去除末尾 `/`（`.rstrip("/")`）。

### 示例

| `api_base` | 实际请求 URL |
|---|---|
| `https://api.deepseek.com` | `https://api.deepseek.com/chat/completions` |
| `https://api.openai.com/v1` | `https://api.openai.com/v1/chat/completions` |
| `http://localhost:4000/v1` | `http://localhost:4000/v1/chat/completions` |
| `https://openrouter.ai/api/v1` | `https://openrouter.ai/api/v1/chat/completions` |

> ⚠️ **注意**：OpenAI 的 API 路径包含 `/v1` 前缀。配置 `api_base` 时**必须包含 `/v1`**，否则 URL 会缺少路径段。

---

## 3. 接入 LiteLLM Proxy

[LiteLLM](https://github.com/BerriAI/litellm) 是一个开源的 LLM 代理，支持 100+ LLM 供应商的统一 OpenAI 兼容接口。

### 3.1 启动 LiteLLM

```bash
# 安装
pip install litellm[proxy]

# 启动（使用配置文件）
litellm --config litellm_config.yaml --port 4000
```

### 3.2 LiteLLM 配置示例

```yaml
# litellm_config.yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: ${OPENAI_API_KEY}
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: ${DEEPSEEK_API_KEY}

general_settings:
  master_key: ${LITELLM_MASTER_KEY}
```

### 3.3 RAG-MCP 侧配置

编辑 `config/settings.yaml`：

```yaml
llm:
  provider: "deepseek"          # provider 字段保持原值（决定初始化逻辑）
  enabled: true
  api_base: "http://localhost:4000/v1"   # 指向 LiteLLM 网关
  api_key_env: "DEEPSEEK_API_KEY"        # 填写 LiteLLM 的 virtual key
  model: "deepseek-chat"                 # LiteLLM 中注册的 model_name
  temperature: 0.1
  max_tokens: 1024
  timeout_seconds: 60.0
```

在 `.env` 中：

```
DEEPSEEK_API_KEY=sk-你的LiteLLM虚拟Key
```

---

## 4. 接入 Synapse

[Synapse](https://github.com/synapsecn/synapse) 是一个企业级 LLM 网关（假设项目使用此网关）。

### 4.1 RAG-MCP 侧配置

```yaml
llm:
  provider: "deepseek"
  enabled: true
  api_base: "https://synapse.your-company.com/v1"
  api_key_env: "DEEPSEEK_API_KEY"
  model: "deepseek-chat"
  temperature: 0.1
  max_tokens: 1024
  timeout_seconds: 60.0
```

在 `.env` 中配置 Synapse 分发的 API Key：

```
DEEPSEEK_API_KEY=sk-synapse-xxxxxxxx
```

### 4.2 Embedding 接入

类似地，如需经过网关的 Embedding 服务：

```yaml
embedding_provider:
  api_base: "https://synapse.your-company.com/v1"
  api_key_env: "ZHIPU_API_KEY"
  model: "text-embedding-3"
```

> 当前 ZhipuEmbeddingProvider 使用智源自己的 API 协议，非 OpenAI 兼容格式。接入 OpenAI 兼容网关的 Embedding 需要新增一个兼容 Provider，或修改 ZhipuEmbeddingProvider 的路径。

---

## 5. 接入 OpenRouter

[OpenRouter](https://openrouter.ai/) 是一个聚合多家 LLM 的 API 网关。

```yaml
llm:
  provider: "deepseek"
  enabled: true
  api_base: "https://openrouter.ai/api/v1"
  api_key_env: "DEEPSEEK_API_KEY"     # 填写 OpenRouter API Key
  model: "deepseek/deepseek-chat"     # OpenRouter 模型标识
  temperature: 0.1
  max_tokens: 1024
  timeout_seconds: 60.0
```

> ⚠️ OpenRouter 的模型名带有前缀（如 `deepseek/deepseek-chat`），与直连时不同。

---

## 6. 直连模式参考

### 6.1 DeepSeek（默认）

```yaml
llm:
  api_base: "https://api.deepseek.com"
  api_key_env: "DEEPSEEK_API_KEY"
  model: "deepseek-chat"
```

### 6.2 OpenAI

```yaml
llm:
  provider: "deepseek"     # 复用 OpenAI 兼容的 Provider
  api_base: "https://api.openai.com/v1"
  api_key_env: "OPENAI_API_KEY"
  model: "gpt-4o"
```

### 6.3 任何 OpenAI 兼容供应商

只要是兼容 `/chat/completions` 端点的供应商，均可通过修改 `api_base` 和 `model` 接入。

---

## 7. 故障排查

| 症状 | 可能原因 | 解决 |
|---|---|---|
| `401 Unauthorized` | API Key 不匹配或过期 | 检查 `.env` 和网关侧的 Key 配置 |
| `404 Not Found` | URL 拼接错误 | 确认 `api_base` 含 `/v1` 前缀，最终 URL 为 `{api_base}/chat/completions` |
| `Connection refused` | 网关未启动 | 检查网关进程是否运行，端口是否正确 |
| `429 Too Many Requests` | 超过速率限制 | 在网关侧调整限流策略，或减小并发数 |
| 返回的模型名不对 | 网关路由配置错误 | 检查网关注册的 `model_name` 与 RAG-MCP 的 `model` 是否一致 |

---

## 8. 相关文档

- [技术文档.md](技术文档.md) — 项目架构与配置系统详解
- [quickstart.md](quickstart.md) — 5 分钟快速上手
- [.env.example](../.env.example) — 环境变量模板
- [settings.yaml.example](../config/settings.yaml.example) — 完整配置模板
