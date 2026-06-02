# RAG-MCP 开源协议选择建议

## 一、当前状态

- **项目**: `rag-mcp` v0.1.0，已公开在 [GitHub](https://github.com/Achernar14/RAG-MCP)
- **当前协议**: **无** — 未包含任何 LICENSE 文件
- **法律状态**: 默认版权保留（All Rights Reserved），他人无权使用、修改或分发

> ⚠️ 没有协议 = 未开源。即使代码公开，法律上仍属于闭源。建议尽快添加协议。

---

## 二、依赖协议分析

### 2.1 直接依赖

| 依赖 | 协议 | 类型 |
|------|------|------|
| chromadb | Apache-2.0 | 宽松 |
| weaviate-client | BSD-3-Clause | 宽松 |
| fastapi | MIT | 宽松 |
| httpx | BSD-3-Clause | 宽松 |
| mcp | MIT | 宽松 |
| pypdf | BSD-3-Clause | 宽松 |
| uvicorn | BSD-3-Clause | 宽松 |
| pydantic | MIT | 宽松 |
| pyyaml | MIT | 宽松 |
| python-dotenv | BSD-3-Clause | 宽松 |
| redis | MIT | 宽松 |
| pytest | MIT | 宽松 |
| streamlit | Apache-2.0 | 宽松 |

### 2.2 关键传递依赖

| 依赖 | 协议 | 注意事项 |
|------|------|----------|
| onnxruntime | MIT | 宽松 |
| tokenizers | Apache-2.0 | 宽松 |
| grpcio | Apache-2.0 | 宽松 |
| numpy | BSD-3-Clause + 多许可 | 宽松 |
| tqdm | **MPL-2.0 AND MIT** | 弱传染（见下） |
| orjson | **MPL-2.0 AND (Apache-2.0 OR MIT)** | 可按 Apache-2.0 使用 |

### 2.3 结论

- **无 GPL/AGPL 等强传染协议** — 不存在 copyleft 合规风险
- **2 个弱传染 (MPL-2.0)** — tqdm、orjson，但作为库引用（非修改源码）不受限制
- **结论**: 可以自由选择任何协议，不受依赖约束

---

## 三、协议对比

### 3.1 候选协议

| 协议 | 类型 | 专利授权 | 商业友好 | 生态匹配度 | 复杂度 |
|------|------|---------|---------|-----------|--------|
| **MIT** | 宽松 | ❌ | ✅ | ★★★★★ | 极简 |
| **Apache-2.0** | 宽松 | ✅ | ✅ | ★★★★ | 中等 |
| **BSD-3-Clause** | 宽松 | ❌ | ✅ | ★★★ | 简单 |
| **GPL-3.0** | 强传染 | ✅ | ⚠️ | ★★ | 复杂 |
| **AGPL-3.0** | 网络传染 | ✅ | ⚠️ | ★ | 复杂 |
| **SSPL** | 源码可用 | ❌ | ⚠️ | ★ | 复杂 |
| **BSL** | 商业源码 | ❌ | ✅ | ★ | 复杂 |

### 3.2 各协议对 RAG-MCP 的影响

#### MIT（推荐 ✅）

```
做什么都行，保留版权声明即可。
```

- 他人可自由使用、修改、分发、商用
- 需保留版权和许可声明
- 最适合工具类/基础设施类项目
- Python 生态主流（fastapi、pydantic、mcp 均用 MIT）

**适用场景**: 希望项目被广泛采用，吸引贡献者，建立生态。

#### Apache-2.0

```
做什么都行，保留版权和变更说明。包含专利授权保护。
```

- 与 MIT 类似的宽松许可
- 额外提供**专利授权**保护（贡献者授予专利使用权）
- 要求保留 NOTICE 文件（如有）
- chromadb（最重依赖）采用此协议

**适用场景**: 涉及专利风险、企业级使用、与 Apache 基金会生态对齐。

#### GPL-3.0

```
你可以用，但衍生作品必须也开源（同一协议）。
```

- 强传染：修改后的代码必须以 GPL-3.0 发布
- 防止闭源商业分支
- 提供专利授权保护

**适用场景**: 强烈要求衍生贡献回馈社区，防止商业闭源。

#### AGPL-3.0

```
你通过网络提供服务也算"分发"，也必须开源。
```

- GPL-3.0 + 网络服务条款
- 即使不分发代码，仅提供 SaaS 服务也必须开源修改
- 对 RAG 即服务（RAGaaS）场景影响大

**适用场景**: 防止云厂商白嫖代码提供商业 RAG 服务。

#### BSL（Business Source License）

```
早期商业保护，一段时间后转为开源。
```

- 设定变更日期（通常 3 年），之后自动转为 Apache-2.0
- 在变更日期前，生产使用需购买许可证
- MongoDB、Redis 曾采用此模式

**适用场景**: 计划商业化，需要时间窗口。

---

## 四、推荐方案

### 4.1 首选推荐：MIT

**理由：**

| 维度 | 分析 |
|------|------|
| **生态一致** | 核心依赖 fastapi、pydantic、mcp、redis 均为 MIT |
| **项目性质** | RAG-MCP 是基础设施/工具层，越宽松越容易被集成 |
| **目标用户** | AI 开发者、Agent 开发者，对宽松协议接受度最高 |
| **社区建设** | MIT 门槛最低，利于吸引贡献 |
| **MCP 生态** | MCP 协议本身是 MIT，作为 MCP Server 保持一致 |
| **学术背景** | 华南师范大学项目，MIT 是学术界最常用的宽松协议 |

**操作步骤：**

1. 在项目根目录创建 `LICENSE` 文件
2. 内容使用 MIT 协议模板（见下方）
3. 在 `README.md` 中添加许可证说明（已有）

### 4.2 备选方案：Apache-2.0

如果关注专利保护，选 Apache-2.0：

| 考虑因素 | 说明 |
|----------|------|
| 专利保护 | 贡献者明确授予专利使用权 |
| 企业友好 | 大企业法务对 Apache-2.0 更熟悉 |
| 生态匹配 | chromadb 使用 Apache-2.0 |

### 4.3 不推荐：GPL/AGPL

| 原因 | 说明 |
|------|------|
| 与 MCP 生态冲突 | MCP SDK 是 MIT，GPL 会限制集成自由度 |
| 阻碍 Agent 集成 | AI Agent 开发者通常不愿引入 GPL 组件 |
| 阻碍商业化 | 潜在企业用户可能因 GPL 放弃使用 |

---

## 五、MIT 协议模板

创建 `LICENSE` 文件，内容如下（将 `<YEAR>` 和 `<NAME>` 替换为实际值）：

```
MIT License

Copyright (c) <YEAR> Chengfei Long (longjincf) and Boyuan Zeng (Achernar14)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 六、实施清单

- [ ] 确认协议选择（推荐 MIT）
- [ ] 创建 `LICENSE` 文件
- [ ] 在 `pyproject.toml` 中声明 `license`
- [ ] 在 `README.md` 中确认许可说明已指向 LICENSE 文件
- [ ] 提交并在 GitHub 上确认协议标识显示正确

---

## 七、参考资源

- [Choose a License](https://choosealicense.com/) — GitHub 官方协议选择工具
- [SPDX License List](https://spdx.org/licenses/) — 标准协议标识符
- [Open Source Guide: Legal](https://opensource.guide/legal/) — 开源法律指南
