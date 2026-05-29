# RAG-MCP 敏感信息审计报告与解决方案

## 审计范围

扫描项目中所有可能包含 API Key、Token、密码等敏感信息的文件，对照现有 `.gitignore` 与配置加载机制，识别泄露风险并提出解决方案。

---

## 1. 泄露风险清单

### 1.1 CRITICAL — `.claude/` 目录下硬编码 Auth Token（3处）

| 文件 | 行 | 泄露内容 |
|---|---|---|
| `.claude/settings.json` | 16 | `ANTHROPIC_AUTH_TOKEN: 28c29531...df613eb.UbJZIvbl2pBVJRQJ` |
| `.claude/settings.local.json` | 13 | 同上（重复拷贝） |
| `.claude/settings copy.json` | 12 | 同上（重复拷贝） |

这三份文件都包含完整的认证 Token 和 API Base URL `https://open.bigmodel.cn/api/anthropic`。

**风险分析：**

- 工作区根目录 `/home/testadmin/workspace/rag/` **没有 `.gitignore`**
- 如果该目录被初始化为 git 仓库或被任何版本管理工具扫描，Token 将直接暴露
- `settings copy.json` 是冗余备份文件，属于不必要的风险扩散
- 同一 Token 出现 3 次，任一泄露即全盘泄露

### 1.2 MEDIUM — 源码中硬编码 API Fallback URL（2处）

| 文件 | 行 | 内容 |
|---|---|---|
| `backend/src/rag_mcp/infrastructure/embedding/zhipu_embedding.py` | 22 | `api_base or "https://open.bigmodel.cn/api/paas/v4"` |
| `backend/src/rag_mcp/infrastructure/llm/deepseek_llm.py` | 24 | `api_base or "https://api.deepseek.com"` |

**风险分析：**

- URL 本身不是密钥，但暴露了服务商和 API 端点结构
- 更严重的是：当 YAML 配置缺失或被误删时，代码会 **静默回退** 到硬编码地址，绕过配置体系，可能导致请求打到错误环境
- 正确做法应是配置缺失时立即报错，而非猜测默认值

### 1.3 LOW — `config/settings.yaml` 和 `config/settings.yaml.example` 中的 API URL

| 文件 | 行 | 内容 |
|---|---|---|
| `config/settings.yaml` | 10, 18 | Zhipu / DeepSeek API Base URL |
| `config/settings.yaml.example` | 10, 18 | 同上 |

**风险分析：**

- `settings.yaml` 已在 `.gitignore` 中排除，不会提交 — **安全**
- `settings.yaml.example` 是模板，包含公开 URL（非密钥） — **可接受**
- 两份文件中的 `api_key_env` 字段存储的是 **环境变量名**（如 `ZHIPU_API_KEY`），不是实际密钥 — **设计正确**

### 1.4 INFO — `.env` 文件状态

| 文件 | 状态 |
|---|---|
| `.env` | 已在 `.gitignore`，内容为占位符 — **安全** |
| `.env.example` | 已跟踪，内容为 `your_xxx_api_key_here` 占位符 — **安全** |

---

## 2. 现有防护机制评估

### 2.1 做得好的部分

```
✅ .env 和 .env.* 已加入 .gitignore（!.env.example 例外）
✅ config/settings.yaml 已加入 .gitignore
✅ API Key 通过 api_key_env 间接引用环境变量，不在 YAML 中存明文
✅ require_env_value() 强制从 os.getenv() 读取，缺失时抛 ConfigurationError
✅ .env.example 仅含占位符
✅ Redis 密码同样走 password_env → os.getenv() 间接路径
```

### 2.2 防护缺口

```
❌ 工作区根目录无 .gitignore，.claude/ 目录未被保护
❌ .claude/settings.json 含明文 Token，无任何排除机制
❌ settings copy.json 是冗余文件，增加攻击面
❌ settings-recommended.json 含 Base URL（无 Token），但 "recommended" 暗示可分享
❌ 源码中 API URL 作为 fallback 硬编码，绕过配置体系
❌ 项目级 .gitignore 未覆盖 .claude/ 目录
```

---

## 3. 敏感信息分布图

```
workspace/rag/                                  ← 无 .gitignore !
├── .claude/
│   ├── settings.json           🔴 明文 Token
│   ├── settings.local.json     🔴 明文 Token（重复）
│   ├── settings copy.json      🔴 明文 Token（重复）
│   └── settings-recommended.json  🟡 Base URL
│
└── RAG-MCP/                                    ← 有 .gitignore ✅
    ├── .env                    🟢 已排除，占位符
    ├── .env.example            🟢 已跟踪，占位符
    ├── config/
    │   ├── settings.yaml       🟢 已排除
    │   └── settings.yaml.example  🟢 已跟踪，无密钥
    ├── backend/src/rag_mcp/infrastructure/
    │   ├── embedding/zhipu_embedding.py    🟡 硬编码 fallback URL
    │   └── llm/deepseek_llm.py            🟡 硬编码 fallback URL
    └── .gitignore               ✅ 覆盖 .env, settings.yaml
```

---

## 4. 解决方案

### 4.1 方案一：立即修复 — Token 轮换 + 文件清理（必须执行）

**Step 1：轮换已泄露的 Token**

```
1. 前往 open.bigmodel.cn 控制台
2. 作废旧 Token：28c29531...df613eb.UbJZIvbl2pBVJRQJ
3. 生成新 Token
```

**Step 2：清理 `.claude/` 下的冗余文件**

```bash
# 删除冗余备份
rm ".claude/settings copy.json"

# 确保 settings-recommended.json 不含任何密钥（当前仅含 URL，可保留）
```

**Step 3：将 Token 从 `.claude/settings.json` 迁移到环境变量**

当前 `.claude/settings.json` 内容：
```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "28c29531...（明文密钥）",
    "ANTHROPIC_BASE_URL": "https://open.bigmodel.cn/api/anthropic"
  }
}
```

改造后：
```json
{
  "permissions": {
    "allow": [
      "Bash(ls -la ~/workspace/flygpt/)",
      "Read(//home/testadmin/workspace/flygpt/**)"
    ]
  }
}
```

将敏感值移至 shell profile 或独立环境文件：

```bash
# ~/.bashrc 或 ~/.zshrc（用户级，不进版本控制）
export ANTHROPIC_AUTH_TOKEN="<new-token>"
export ANTHROPIC_BASE_URL="https://open.bigmodel.cn/api/anthropic"
```

或者创建 `.claude/.env`（需配合 hook 或 shell 加载）：

```bash
# .claude/.env
ANTHROPIC_AUTH_TOKEN=<new-token>
ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
```

---

### 4.2 方案二：添加 `.gitignore` 防护网

**在工作区根目录创建 `.gitignore`：**

```gitignore
# ------------------------------------------------------------------------------
# IDE / Editor / Tooling
# ------------------------------------------------------------------------------
.claude/
.idea/
.vscode/

# ------------------------------------------------------------------------------
# Environment and secrets
# ------------------------------------------------------------------------------
.env
.env.*
!.env.example
*.secret
*.key
```

**同时在 RAG-MCP 项目 `.gitignore` 中追加：**

```gitignore
# Claude Code tooling (may contain auth tokens)
.claude/
```

---

### 4.3 方案三：消除源码中的硬编码 Fallback URL

**现状（zhipu_embedding.py:22）：**
```python
self.api_base = (api_base or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
```

**改造：缺失时立即报错，不做静默猜测**
```python
if not api_base:
    raise ConfigurationError("zhipu embedding api_base is not configured")
self.api_base = api_base.rstrip("/")
```

同理 `deepseek_llm.py:24`：
```python
if not api_base:
    raise ConfigurationError("deepseek llm api_base is not configured")
self.api_base = api_base.rstrip("/")
```

这确保了：
- 配置缺失不会静默回退到硬编码地址
- 所有的 API 端点必须通过 `settings.yaml` 显式配置
- 生产环境与测试环境的端点完全由配置文件控制

---

### 4.4 方案四：引入 `settings.local.yaml` 本地覆盖机制

当前项目已有 `settings.yaml`（gitignored）和 `settings.yaml.example`（tracked）。可以进一步增加 **分层配置**：

```
config/
├── settings.yaml              # 本地实际配置（gitignored）
├── settings.local.yaml        # 本地覆盖层（gitignored，最高优先级）
└── settings.yaml.example      # 模板（tracked，无敏感信息）
```

**在 `core/settings.py` 中增加覆盖逻辑：**

```python
def load_settings(path: str | Path | None = None) -> Settings:
    load_dotenv(DOTENV_PATH)

    settings_path = _resolve_settings_path(path)

    raw = yaml.safe_load(settings_path.read_text(encoding="utf-8")) or {}

    # 本地覆盖层（可选）
    local_override = settings_path.parent / "settings.local.yaml"
    if local_override.exists():
        local_raw = yaml.safe_load(local_override.read_text(encoding="utf-8")) or {}
        raw = _deep_merge(raw, local_raw)

    return Settings.model_validate(raw)
```

**`.gitignore` 追加：**
```gitignore
config/settings.local.yaml
```

**使用场景：**

| 文件 | 用途 | 版本控制 |
|---|---|---|
| `settings.yaml.example` | 团队共享模板 | 跟踪 |
| `settings.yaml` | 本地完整配置 | 不跟踪 |
| `settings.local.yaml` | 仅覆盖差异项（如切 provider） | 不跟踪 |
| `.env` | API Key 等密钥 | 不跟踪 |

---

### 4.5 方案五：全局检查脚本

创建一个 pre-commit 或 CI 可用的检查脚本，自动扫描敏感信息：

```bash
#!/bin/bash
# scripts/check-secrets.sh
# 用法: ./scripts/check-secrets.sh

echo "Scanning for potential secrets..."

PATTERNS=(
    'sk-[a-zA-Z0-9]{20,}'
    '[a-f0-9]{32}\.[a-zA-Z0-9]{10,}'
    'api_key\s*[:=]\s*["\x27][^"\x27]{10,}'
    'password\s*[:=]\s*["\x27][^"\x27]{4,}'
    'secret\s*[:=]\s*["\x27][^"\x27]{10,}'
    'token\s*[:=]\s*["\x27][^"\x27]{20,}'
)

FOUND=0
for pattern in "${PATTERNS[@]}"; do
    # 排除 .git, .env.example, settings.yaml.example
    matches=$(grep -rn -E "$pattern" \
        --include="*.py" --include="*.yaml" --include="*.json" --include="*.env" \
        --exclude-dir=".git" --exclude-dir="node_modules" --exclude-dir=".venv" \
        --exclude="settings.yaml.example" --exclude=".env.example" \
        . 2>/dev/null)
    if [ -n "$matches" ]; then
        echo "FOUND: $pattern"
        echo "$matches"
        FOUND=1
    fi
done

if [ $FOUND -eq 1 ]; then
    echo ""
    echo "ERROR: Potential secrets detected. Do not commit these files."
    exit 1
else
    echo "OK: No secrets detected."
    exit 0
fi
```

---

## 5. 行动计划

| 优先级 | 行动 | 涉及文件 |
|---|---|---|
| **P0 立即** | 轮换 Token `28c29531...` | open.bigmodel.cn 控制台 |
| **P0 立即** | 删除 `.claude/settings copy.json` | `.claude/settings copy.json` |
| **P0 立即** | 从 `.claude/settings.json` 和 `.claude/settings.local.json` 移除 `ANTHROPIC_AUTH_TOKEN`，改为环境变量 | `.claude/settings.json`, `.claude/settings.local.json` |
| **P1 本周** | 工作区根目录创建 `.gitignore`，排除 `.claude/` | `.gitignore`（根目录） |
| **P1 本周** | RAG-MCP `.gitignore` 追加 `.claude/` | `RAG-MCP/.gitignore` |
| **P2 迭代内** | 移除源码中硬编码 fallback URL，改为强制报错 | `zhipu_embedding.py`, `deepseek_llm.py` |
| **P2 迭代内** | 引入 `settings.local.yaml` 分层覆盖机制 | `core/settings.py`, `.gitignore` |
| **P3 长期** | 添加 `scripts/check-secrets.sh` 并集成到 pre-commit | 新文件 |

---

## 6. 敏感信息管理原则

```
┌──────────────────────────────────────────────────────────────────┐
│                    敏感信息三层分离原则                            │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: 代码（tracked）                                        │
│  ┌──────────────────────────────────┐                            │
│  │ settings.yaml.example            │ ← 仅含占位符和公开 URL      │
│  │ .env.example                     │ ← 仅含占位符                │
│  │ Python 源码                      │ ← 不含任何密钥或 fallback   │
│  └──────────────────────────────────┘                            │
│                                                                  │
│  Layer 2: 本地配置（gitignored）                                  │
│  ┌──────────────────────────────────┐                            │
│  │ settings.yaml                    │ ← API URL, 模型名, 参数     │
│  │ settings.local.yaml              │ ← 差异覆盖（可选）          │
│  └──────────────────────────────────┘                            │
│                                                                  │
│  Layer 3: 密钥（环境变量 / Secret Manager）                       │
│  ┌──────────────────────────────────┐                            │
│  │ .env (gitignored)                │ ← API Key 实际值            │
│  │ Shell environment                │ ← ANTHROPIC_AUTH_TOKEN 等   │
│  │ .claude/ (gitignored)            │ ← IDE 工具 Token            │
│  └──────────────────────────────────┘                            │
│                                                                  │
│  核心规则:                                                       │
│  ✓ 代码只引用变量名（api_key_env: "ZHIPU_API_KEY"）              │
│  ✓ 配置文件只存非敏感参数（URL、模型名、超时）                     │
│  ✓ 密钥只存在环境变量中，通过 os.getenv() 运行时读取               │
│  ✓ 每层独立 gitignore 保护                                        │
└──────────────────────────────────────────────────────────────────┘
```
