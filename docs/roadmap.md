# RAG-MCP 项目补全方向

## 当前状态概览

**截至版本：** V2.11 (2026-05-18)

- 总体工程完成度：约 **85%**
- 核心业务主链路完成度：约 **88%**
- 当前状态：**第一阶段收口版本**，可进入维护与下一阶段迭代

---

## 补全优先级总览

```
高优先级 (P0) ────────────────────────────────────────┐
├── 摄取增强与多集合一致性                            │
├── Provider 体系扩展 (Vision/Evaluator)              │
└── 多模态摄取闭环                                    │
                                                        │
中优先级 (P1) ────────────────────────────────────────┤
├── 高级生成评测                                      │
├── Dashboard 深度观测增强                            │
└── Trace 聚合查询优化                                │
                                                        │
低优先级 (P2) ────────────────────────────────────────┤
├── MCP SDK 收口与 legacy 兼容层退役                  │
├── 更重型部署化与运行时封装                          │
└── 更完整的多集合模型                                │
                                                        │
──────────────────────────────────────────────────────┘
```

---

## 一、高优先级补全项 (P0)

### 1.1 摄取增强与多集合一致性

**目标：** 完善摄取流程的稳定性和可靠性，支持多集合场景。

**当前状态：**
- ✅ 基础摄取链路已完成
- ✅ 基础幂等性已实现 (同路径同内容跳过)
- ✅ 基础文件元数据增强已完成
- ⚠️ 深度 metadata enrichment 未实现
- ⚠️ 强重建策略需完善
- ⚠️ 多集合一致性未实现

**待补全内容：**

| 任务项 | 描述 | 验收标准 |
|--------|------|----------|
| 强重建策略 | 完善 force_rebuild 逻辑，支持集合级重建 | 可一键重建指定集合 |
| 版本判断优化 | 基于内容指纹的精确版本检测 | 内容不变时零重复索引 |
| 失败重试机制 | 摄取失败时的重试与部分成功处理 | 失败文档可隔离重试 |
| Metadata Enrichment | 深度元数据提取 (标题、作者、日期等) | PDF 文档元数据完整提取 |
| Chunk Refinement | 语义级切分，避免截断语义 | 语义边界切分准确率 >90% |
| 多集合一致性 | 确保多集合操作的原子性和一致性 | 跨集合操作可回滚 |

**预计工作量：** 3-4 周

---

### 1.2 Provider 体系扩展

**目标：** 扩展 Provider 抽象到 Vision 和 Evaluator，实现真正的可插拔架构。

**当前状态：**
- ✅ Embedding Provider (zhipu, hash)
- ✅ LLM Provider (deepseek, stub)
- ✅ Rerank Provider (lexical)
- ✅ Provider Factory 统一入口
- ❌ Vision Provider (仅骨架)
- ❌ Evaluator Provider (未实现)

**待补全内容：**

| Provider | 实现内容 | 接口定义 |
|----------|----------|----------|
| Vision Provider | 图像描述生成、图文联合理解 | `describe_image(path, prompt) -> VisionCaptionResult` |
| Evaluator Provider | 答案相关性、Faithfulness、引用正确率 | `evaluate_answer(query, answer, context) -> EvaluationMetrics` |
| Rerank Provider 扩展 | 支持模型型 Rerank (如 BGE, Cohere) | `rerank(query, candidates, top_k) -> list[RetrievalResult]` |

**接口设计要求：**
```python
class VisionLlmProvider(ABC):
    @abstractmethod
    async def describe_image(
        self,
        image_path: str,
        prompt: str | None = None
    ) -> VisionCaptionResult:
        """生成图像描述，返回 caption 和元数据"""
        pass

class EvaluatorProvider(ABC):
    @abstractmethod
    async def evaluate_answer(
        self,
        query: str,
        answer: str,
        contexts: list[str],
        sources: list[SourceTrace]
    ) -> AnswerEvaluationMetrics:
        """评估生成答案的质量"""
        pass

class ModelRerankerProvider(ABC):
    @abstractmethod
    async def rerank(
        self,
        query: str,
        candidates: list[RetrievalResult],
        top_k: int
    ) -> list[RetrievalResult]:
        """使用模型进行重排序"""
        pass
```

**配置扩展：**
```yaml
vision_llm:
  provider: openai  # openai, claude, azure, etc.
  enabled: true
  model: gpt-4o
  api_key_env: OPENAI_API_KEY

evaluator:
  provider: openai
  enabled: true
  model: gpt-4o
  metrics:
    - relevance
    - faithfulness
    - citation_accuracy

rerank:
  provider: bge  # lexical, bge, cohere
  enabled: true
  model: BAAI/bge-reranker-v2-m3
```

**预计工作量：** 2-3 周

---

### 1.3 多模态摄取闭环

**目标：** 实现 PDF 图像提取、描述生成和图文联合检索。

**当前状态：**
- ✅ 多模态元数据骨架已预留
- ❌ 真实图像提取未实现
- ❌ 图像描述生成未实现
- ❌ 图文关联策略未定义

**待补全内容：**

| 阶段 | 任务 | 描述 |
|------|------|------|
| 1. 图像提取 | PDF 解析提取图像 | 使用 pdfplumber/PyPDF2 提取图像 |
| 2. 图像存储 | 图像文件持久化 | 存储到 `data/assets/images/` |
| 3. 元数据记录 | 图像元数据入库 | 记录路径、尺寸、格式、位置 |
| 4. 描述生成 | Vision LLM 生成 caption | 调用 Vision Provider |
| 5. 关联策略 | 图文 chunk 关联 | 图像 caption 与相邻文本 chunk 关联 |
| 6. 检索溯源 | 返回结果带图像信息 | sources 中包含图像引用 |

**数据结构设计：**
```python
@dataclass
class ImageAsset:
    id: str
    document_id: str
    file_path: str
    page_number: int
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    width: int
    height: int
    format: str  # png, jpg, etc.
    caption: str | None = None
    caption_generated_at: datetime | None = None
    associated_chunk_ids: list[str] = field(default_factory=list)
```

**检索返回增强：**
```python
{
    "answer": "...",
    "sources": [
        {
            "type": "text",
            "content": "...",
            "document_id": "...",
            "page": 1
        },
        {
            "type": "image",
            "image_path": "data/assets/images/doc1_img1.png",
            "caption": "流程图展示了...",
            "document_id": "...",
            "page": 2
        }
    ]
}
```

**预计工作量：** 2-3 周

---

## 二、中优先级补全项 (P1)

### 2.1 高级生成评测

**目标：** 建立生成答案质量的回归评估体系。

**当前状态：**
- ✅ 检索评测 MVP (HitRate@K, MRR)
- ❌ 生成质量评测未实现

**待补全内容：**

| 指标 | 描述 | 实现方式 |
|------|------|----------|
| Relevance | 答案与问题的相关性 | LLM-as-Judge 评分 |
| Faithfulness | 答案与上下文的一致性 | 检测幻觉和编造 |
| Citation Accuracy | 引用的准确性 | 验证引用来源存在性 |
| Completeness | 答案的完整性 | 检查是否遗漏关键信息 |

**评测流程设计：**
```
Query → Retrieval → Generation → Evaluation
                                      ↓
                               ┌─────────────┐
                               │ Relevance   │
                               │ Faithfulness│
                               │ Citation    │
                               │ Completeness│
                               └─────────────┘
                                      ↓
                               Evaluation Report
```

**配置示例：**
```yaml
evaluation:
  generator:
    enabled: true
    metrics:
      - relevance
      - faithfulness
      - citation_accuracy
    judge_provider:
      provider: openai
      model: gpt-4o
    golden_set_path: data/evaluations/answer_golden_set.json
```

**预计工作量：** 2 周

---

### 2.2 Dashboard 深度观测增强

**目标：** 从管理面板升级为运维观测平台。

**当前状态：**
- ✅ 6 页基础 Dashboard
- ✅ 基础 trace 浏览和详情
- ⚠️ 深度排障能力不足

**待补全内容：**

| 页面 | 增强内容 |
|------|----------|
| Traces | 添加 trace 关联图、调用链可视化 |
| Answers | 添加 Provider/Prompt A/B 对比视图 |
| Evaluations | 添加失败样本聚合、按维度筛选 |
| Ingestion | 添加摄取进度监控、失败原因聚合 |
| Documents | 添加 chunk 质量分析、索引健康度 |
| Overview | 添加系统健康度评分、SLA 指标 |

**新增观测维度：**
- Provider 调用成功率与耗时分布
- Prompt 版本效果对比
- Query 类型分析与命中率
- Failure Hotspot 聚合分析

**预计工作量：** 2-3 周

---

### 2.3 Trace 聚合查询优化

**目标：** 优化大规模 trace 数据的查询性能。

**当前状态：**
- ✅ JSONL 持久化
- ⚠️ 大规模数据查询慢

**优化方向：**
1. 添加时间范围索引
2. 实现分页查询
3. 支持聚合统计 (按类型/状态/Provider)
4. 考虑 SQLite 后端选项

**预计工作量：** 1 周

---

## 三、低优先级补全项 (P2)

### 3.1 MCP SDK 收口与兼容层退役

**目标：** 完全迁移到官方 MCP SDK，移除 legacy 代码。

**当前状态：**
- ✅ SDK server 已作为默认入口
- ⚠️ legacy 协议层仍保留

**待完成：**
1. 移除 `protocol.py` 中的 legacy 实现
2. 统一错误格式
3. 添加 MCP 资源 (resources) 支持
4. 添加 Prompt 模板支持

**预计工作量：** 1-2 周

---

### 3.2 部署化与运行时封装

**目标：** 提供生产级部署方案。

**待完成：**
- Docker Compose 配置
- 健康检查端点
- 优雅关闭机制
- 日志轮转配置
- 监控指标暴露 (Prometheus)

**预计工作量：** 1-2 周

---

## 四、实施路线图

### Phase 1: 稳定性增强 (4-6 周)

```
Week 1-2: 摄取增强与多集合一致性
Week 3-4: Provider 体系扩展
Week 5-6: 多模态摄取闭环
```

### Phase 2: 能力扩展 (3-4 周)

```
Week 7-8: 高级生成评测
Week 9-10: Dashboard 深度观测
Week 11: Trace 查询优化
```

### Phase 3: 工程收敛 (2-3 周)

```
Week 12-13: MCP SDK 收口
Week 14: 部署化封装
```

---

## 五、贡献指南

### 5.1 优先参与方向

欢迎社区贡献，优先级排序：

1. **Provider 扩展** - 接入更多 Embedding/LLM/Rerank Provider
2. **评测增强** - 实现新的评测指标
3. **Dashboard 组件** - 开发新的可视化组件
4. **文档完善** - 补充使用案例和最佳实践
5. **测试覆盖** - 提高测试覆盖率

### 5.2 提交规范

- 遵循 Conventional Commits
- 新增功能需包含测试
- 修改公共接口需更新文档
- Provider 扩展需符合接口规范

---

## 六、封版边界

### 当前版本 (V2.11) 明确边界

**不再继续扩张：**
- ❌ 真实 Vision Provider
- ❌ LLM-as-Judge 评测栈
- ❌ 多集合复杂模型
- ❌ MCP 扩展能力 (resources/prompts)

**转入下一阶段：**
- ⏭️ 多模态真实处理链路
- ⏭️ 高级生成质量评测
- ⏭️ MCP legacy 兼容层退役

---

## 七、成功标准

### 7.1 阶段性验收标准

| 阶段 | 标准 |
|------|------|
| Phase 1 | 所有 P0 任务完成，核心业务无回归 |
| Phase 2 | Dashboard 可覆盖管理/调试/观测/评测四类动作 |
| Phase 3 | 可通过单一 Docker 镜像部署到生产环境 |

### 7.2 最终验收标准

- [ ] 摄取成功率 > 99%
- [ ] 检索响应时间 P99 < 2s
- [ ] 生成回退率 < 5%
- [ ] 测试覆盖率 > 80%
- [ ] 文档完整性 > 90%

---

*本文档基于 `技术文档.md` V2.11 整理，随项目演进持续更新*
