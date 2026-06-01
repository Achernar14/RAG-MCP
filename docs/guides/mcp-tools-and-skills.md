# MCP 工具与 Skill 概念详解

## 1. MCP Tools 与 Skill 的关系

在 MCP 生态中存在一个容易混淆的概念：**Tool（工具）** 和 **Skill（技能）**。本文解释两者的区别，以及它们在 RAG-MCP 项目中的定位。

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   MCP Tools (工具)                    Skill (技能)                   │
│   ───────────────                     ───────────                   │
│                                                                     │
│   定义: MCP 协议中的原语              定义: LLM 客户端侧的概念       │
│   "服务器能做什么操作"                "LLM 学会了怎么组合操作"       │
│                                                                     │
│   位置: RAG-MCP 服务器端              位置: LLM 客户端（Claude 等）  │
│   实现者: 开发者硬编码                实现者: LLM 运行时自动推断      │
│                                                                     │
│   粒度: 单个原子操作                  粒度: 多个工具的组合策略        │
│   例: knowledge_query()              例: "先导入文档 → 再查询"      │
│       knowledge_ingest()                  "先查状态 → 决定是否重建"  │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────┐      │
│   │  RAG-MCP 提供 15 个 Tools                              │      │
│   │  LLM 通过组合这些 Tools 形成 Skills                     │      │
│   └─────────────────────────────────────────────────────────┘      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 一句话总结

> **Tool 是服务器暴露的能力，Skill 是 LLM 组合 Tool 完成复杂任务的能力。RAG-MCP 提供 Tool，LLM 自行习得 Skill。**

---

## 2. Tool 详解：15 个原子操作

### 2.1 什么是 Tool

Tool 是 MCP 协议中定义的标准原语。每个 Tool 有：

| 属性 | 说明 | 来源 |
|---|---|---|
| **name** | 工具唯一标识 | Python 函数名 |
| **description** | 工具描述（LLM 看到的） | Python docstring |
| **inputSchema** | 输入参数的 JSON Schema | `Annotated[type, Field(...)]` 自动生成 |
| **outputSchema** | 输出结构的 JSON Schema | 返回类型 Pydantic 模型自动生成 |

### 2.2 Tool 的参数校验

每个 Tool 的参数都有精确的类型约束：

```python
# 整数范围约束
TopK = Annotated[int, Field(ge=1, le=20)]
TraceLimit = Annotated[int, Field(ge=1, le=100)]

# 字符串非空约束
def knowledge_query(
    query: Annotated[str, Field(min_length=1)],  # 不允许空字符串
    top_k: TopK = 5,                              # 1 到 20 之间
) -> QueryResponse: ...
```

对应的 JSON Schema：

```json
{
  "query": { "type": "string", "minLength": 1 },
  "top_k": { "type": "integer", "minimum": 1, "maximum": 20, "default": 5 }
}
```

LLM 在调用前会自动遵守这些约束。如果 LLM 传了 `top_k: 30`，FastMCP 会拒绝并返回校验错误。

### 2.3 15 个 Tool 分类速查

**知识检索类（最常用）：**

| Tool | 何时被 LLM 调用 |
|---|---|
| `knowledge_query` | 用户问了一个问题，需要在知识库中搜索 |
| `generate_answer` | 用户需要一个完整的回答（不只是搜索结果） |
| `knowledge_ingest` | 用户要求导入新文档 |
| `knowledge_status` | 用户想了解知识库的整体情况 |

**文档管理类：**

| Tool | 何时被 LLM 调用 |
|---|---|
| `list_documents` | 用户问"有哪些文档" |
| `get_document_detail` | 用户问"某个文档的具体内容/分块" |
| `get_document_summary` | 用户问"某个文档的概要" |
| `delete_document` | 用户要求删除某个文档 |

**运维评估类：**

| Tool | 何时被 LLM 调用 |
|---|---|
| `list_collections` | 用户问"有哪些集合" |
| `rebuild_collection` | 用户要求重建索引 |
| `run_evaluation` | 用户要求评估检索质量 |
| `list_evaluation_reports` | 用户问"有哪些评估报告" |
| `get_evaluation_report` | 用户问"某个评估报告的详情" |
| `list_traces` | 用户问"最近的调用记录" |
| `get_trace_detail` | 用户问"某次调用的详细过程" |

---

## 3. Skill 详解：LLM 如何组合 Tool

### 3.1 什么是 Skill

Skill 不是 RAG-MCP 服务器端的概念，而是 **LLM 客户端侧的行为模式**。当 LLM 学会了在什么场景下调用哪些 Tool、以什么顺序调用、如何组合结果时，它就形成了一个 Skill。

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   Tool（工具）         Skill（技能）                             │
│   单个原子操作          多个工具的编排策略                         │
│                                                                 │
│   ┌──────────────┐     ┌────────────────────────────────────┐  │
│   │ knowledge_   │     │  Skill: "知识库首次配置"            │  │
│   │   ingest     │────▶│                                    │  │
│   ├──────────────┤     │  1. knowledge_status()  检查状态   │  │
│   │ knowledge_   │     │  2. knowledge_ingest()  导入文档   │  │
│   │   status     │────▶│  3. knowledge_query()   验证检索   │  │
│   ├──────────────┤     │                                    │  │
│   │ knowledge_   │     └────────────────────────────────────┘  │
│   │   query     │────▶┐                                       │
│   └──────────────┘     │  Skill: "回答用户问题"               │
│                        │                                       │
│                        │  1. knowledge_query()  检索相关内容  │
│                        │  2. generate_answer()  生成完整回答  │
│                        │                                       │
│                        └────────────────────────────────────┘  │
│                                                                 │
│   RAG-MCP 提供       LLM 在运行时自动组合形成                    │
│   （开发者编码）      （无需开发者编码）                           │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 RAG-MCP 隐含的 Skill 模式

以下是 LLM 在使用 RAG-MCP 时自然形成的典型 Skill。**这些 Skill 没有在代码中定义**，而是 LLM 根据 Tool 描述和上下文自动推断的。

#### Skill 1：首次知识库配置

```
用户: "帮我导入这几份文档并建立知识库"

LLM 自动编排:
  ① knowledge_status()        → 确认当前知识库为空
  ② knowledge_ingest(path=A)  → 导入第一个文档
  ③ knowledge_ingest(path=B)  → 导入第二个文档
  ④ knowledge_ingest(path=C)  → 导入第三个文档
  ⑤ knowledge_status()        → 确认导入成功，查看统计
  ⑥ knowledge_query("测试")   → 验证检索是否正常工作
```

#### Skill 2：精准问答

```
用户: "RAG-MCP 支持哪些文件格式？"

LLM 自动编排:
  ① knowledge_query("支持哪些文件格式", top_k=3)
     → 返回 3 条相关分块

  LLM 判断：搜索结果已足够回答
  → 直接基于搜索结果组织回复（不再调 generate_answer）

  或者 LLM 判断：需要更完整的回答
  ② generate_answer("RAG-MCP 支持哪些文件格式？", top_k=5)
     → 返回完整的 LLM 生成回答 + 引用来源
```

#### Skill 3：诊断检索质量

```
用户: "为什么搜索 xxx 总是找不到想要的结果？"

LLM 自动编排:
  ① knowledge_status()              → 查看知识库整体状态
  ② list_documents()                → 确认相关文档已导入
  ③ get_document_detail(doc_id)     → 检查文档分块是否合理
  ④ knowledge_query("xxx")          → 实际查询，观察返回结果
  ⑤ run_evaluation()                → 运行评估，查看 Hit Rate / MRR
  ⑥ get_evaluation_report(report_id)→ 分析具体失败用例

  LLM 综合分析后给出诊断建议
```

#### Skill 4：文档生命周期管理

```
用户: "文档 A 内容更新了，帮我重新导入"

LLM 自动编排:
  ① list_documents()                → 找到文档 A 的 document_id
  ② delete_document(doc_id)         → 删除旧版本
  ③ knowledge_ingest(path=A_new)    → 导入新版本
  ④ knowledge_query("测试查询")     → 验证新内容可检索
```

#### Skill 5：系统性评估

```
用户: "帮我全面评估一下检索效果"

LLM 自动编排:
  ① run_evaluation()                → 运行评估
  ② get_evaluation_report(report_id)→ 获取详细报告
  ③ 分析 Hit Rate 和 MRR 指标
  ④ 对失败用例逐一分析
  ⑤ 给出调优建议（如调整 top_k、chunk_size 等）
```

### 3.3 Skill 的三个层次

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  Level 1: 单工具调用                                         │
│  ──────────────────                                         │
│  用户问一个问题 → LLM 调一个 Tool → 返回结果                  │
│  例: knowledge_query("什么是 RAG")                           │
│                                                              │
│  Level 2: 串行工具链                                         │
│  ──────────────────                                         │
│  用户提一个需求 → LLM 按顺序调多个 Tool → 组合结果            │
│  例: knowledge_status → knowledge_ingest → knowledge_query   │
│                                                              │
│  Level 3: 条件分支                                           │
│  ──────────────────                                         │
│  LLM 根据前一个 Tool 的返回值决定下一步做什么                  │
│  例:                                                        │
│    knowledge_status()                                        │
│      ├── 知识库为空？ → knowledge_ingest()                   │
│      └── 知识库非空？ → knowledge_query()                    │
│            ├── 结果充足？ → 直接回答                         │
│            └── 结果不足？ → generate_answer()                │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 为什么不在服务器端定义 Skill

### 4.1 MCP 的设计哲学

MCP 协议有意将 **Tool 定义在服务器端**、将 **Skill（使用策略）留给 LLM 客户端**：

```
服务器端（RAG-MCP）           客户端（LLM）
──────────────────           ──────────────

定义 WHAT:                   决定 HOW:
"我能做什么操作"              "什么时候用、怎么组合"

✅ knowledge_query()         🧠 用户问问题 → 先调 query
✅ knowledge_ingest()        🧠 文档更新 → delete + ingest
✅ knowledge_status()        🧠 先看状态再决定下一步
✅ generate_answer()         🧠 简单问题用 query，复杂问题用 answer
✅ ...
```

这样做的好处：

| 优势 | 说明 |
|---|---|
| **通用性** | 同一组 Tool，不同 LLM（Claude/GPT/Gemini）可以形成不同的 Skill |
| **灵活性** | LLM 可以根据上下文动态调整策略，无需重新编码 |
| **可维护性** | 服务器只需维护 Tool 的正确性，不需要维护"怎么组合"的逻辑 |
| **可扩展性** | 新增 Tool 后，LLM 自动学会将其纳入现有 Skill |

### 4.2 如果确实需要服务器端编排

某些场景下，服务器端预定义 Skill（组合操作）是有意义的：

| 场景 | 方案 | 当前状态 |
|---|---|---|
| 原子操作太多，LLM 调用链过长 | 新增一个组合 Tool（如 `ingest_and_verify`） | ❌ 未实现 |
| 需要事务保证（要么全成功要么全失败） | Use Case 层保证事务性 | ✅ 已在 Use Case 层实现 |
| 需要固定流程（合规/审计要求） | 在 Use Case 中硬编码流程 | ✅ 已在 Use Case 层实现 |

**当前项目的选择是正确的**：Use Case 层处理编排逻辑，MCP Tool 层保持轻量透传，Skill 由 LLM 自行演化。

---

## 5. MCP 三种原语的 Skill 潜力

当前项目仅使用了 MCP Tools。MCP 规范还定义了另外两种原语，它们各自支持不同的 Skill 模式：

### 5.1 Tools（已实现）

```
用户 → LLM → tools/call → 服务器执行 → 返回结果 → LLM 回复
```

**适合：** 主动操作（检索、导入、删除、评估）

### 5.2 Resources（计划中）

```
用户 → LLM → resources/read → 服务器返回文档内容 → LLM 分析
```

**适合：** 被动读取（让 LLM 直接阅读文档原文，而不仅仅是检索摘要）

**未来 Skill 示例：**

```
用户: "帮我检查文档 A 的第三章有没有逻辑问题"

LLM Skill:
  ① list_documents() → 找到文档 A
  ② resources/read("rag-mcp://documents/abc123/chunks?range=30-50")
     → 直接阅读第三章的所有分块原文
  ③ 分析逻辑问题并给出建议
```

### 5.3 Prompts（计划中）

```
用户 → LLM → prompts/list → 发现可用模板
用户 → LLM → prompts/get("answer_with_citations") → 获取提示词
```

**适合：** 标准化的交互模板（让用户或 LLM 选用预定义的提示词策略）

**未来 Skill 示例：**

```
用户: "用学术风格回答这个问题"

LLM Skill:
  ① prompts/list() → 发现 "academic_answer" 模板
  ② prompts/get("academic_answer") → 获取模板内容
  ③ 使用模板生成学术风格的回答
```

---

## 6. Tool 与 Skill 的对比总结

```
┌──────────────────┬──────────────────────┬──────────────────────┐
│                  │  Tool（工具）         │  Skill（技能）        │
├──────────────────┼──────────────────────┼──────────────────────┤
│ 定义位置         │ 服务器端（代码）      │ 客户端（LLM 运行时）  │
│ 定义方式         │ Python 函数 + 注解    │ LLM 自动推断          │
│ 数量             │ 15 个（固定）         │ 无限（持续演化）       │
│ 粒度             │ 单个原子操作          │ 多工具组合策略         │
│ 修改方式         │ 改代码、重新部署      │ 无需修改，LLM 自适应   │
│ 可测试性         │ 单元测试 + 集成测试   │ 端到端评估             │
│ MCP 协议支持     │ ✅ tools/call         │ 无（客户端行为）       │
│ 本项目实现       │ ✅ sdk_server.py      │ ✅ LLM 自动形成        │
└──────────────────┴──────────────────────┴──────────────────────┘
```

---

## 7. 扩展阅读

| 主题 | 文档 |
|---|---|
| MCP 工具注册机制与通信协议 | [mcp-protocol.md](./mcp-protocol.md) |
| Function Calling 完整链路 | [function-calling.md](./function-calling.md) |
| 项目架构分层 | [architecture-mvc.md](./architecture-mvc.md) |
| Embedding 与检索结构 | [embedding-structure.md](./embedding-structure.md) |
| 路线图（Resources/Prompts 规划） | [../roadmap.md](../roadmap.md) |
