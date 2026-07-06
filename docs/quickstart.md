# RAG-MCP 快速上手（5 分钟）

本文档帮你在 5 分钟内从零跑通 RAG-MCP：安装 → 配置 → 摄入文档 → 查询 → 接入 Claude Desktop。

> 更深的架构理解请参考 [技术文档.md](技术文档.md)；后续开发路线见 [开发方向调整.md](开发方向调整.md)。

---

## 前置条件

- Python ≥ 3.11
- 一个 LLM / Embedding 供应商的 API Key（默认用 DeepSeek + 智源）
- （可选）Claude Desktop，用于体验 MCP 工具调用

---

## 第 1 步：安装项目

```bash
cd backend
pip install -e .

# 可选：开发依赖（测试、Dashboard）
pip install -e ".[dev]"
```

`pip install -e .` 会以"可编辑模式"安装 `rag_mcp` 包，之后 `python -m rag_mcp.mcp.server` 可在任意目录调用。

---

## 第 2 步：配置环境变量

在**项目根目录**（`RAG-MCP/`，不是 `backend/`）复制并填写：

```bash
cp .env.example .env
```

编辑 `.env`，填入真实 Key：

```
DEEPSEEK_API_KEY=sk-你的真实key
ZHIPU_API_KEY=你的真实key
```

- `DEEPSEEK_API_KEY`：用于生成式问答（[获取](https://platform.deepseek.com/)）
- `ZHIPU_API_KEY`：用于文档向量化（[获取](https://open.bigmodel.cn/)）

> 项目默认配置（`config/settings.yaml`）使用 Chroma 本地向量库，无需任何外部数据库服务。

---

## 第 3 步：摄入一份文档

启动 REST 服务（用于摄入和查询）：

```bash
# 在项目根目录执行
python -m uvicorn rag_mcp.main:app --host 127.0.0.1 --port 8000
```

> 若 `rag_mcp` 未在 PATH 中可导入，可改用 `cd backend && python -m uvicorn rag_mcp.main:app`。

新开一个终端，摄入项目自带的技术文档：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/ingest ^
  -H "Content-Type: application/json" ^
  -d "{\"path\": \"docs/技术文档.md\"}"
```

（Linux/macOS 把 `^` 换成 `\`，且路径用绝对路径更稳妥，如 `d:/PersonalProject/RAG-MCP/docs/技术文档.md`）

预期返回类似：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "document_id": "...",
    "chunk_count": 18,
    "ingestion_action": "created",
    "trace_id": "..."
  },
  "trace_id": "..."
}
```

也可以用一键脚本（无需手写 curl）：

```bash
python scripts/quick_ingest.py --path docs/技术文档.md
# 摄入整个目录：
python scripts/quick_ingest.py --path docs/ --recursive
```

---

## 第 4 步：发起一次查询

```bash
curl -X POST http://127.0.0.1:8000/api/v1/query ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"Skill 是怎么注册和启用的？\", \"top_k\": 5}"
```

返回的 `data.results` 是检索到的文本片段，`data.sources` 是带来源路径的结构化引用。

想要直接生成回答（带 LLM 总结 + 引用）：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/answers/generate ^
  -H "Content-Type: application/json" ^
  -d "{\"query\": \"Skill 是怎么注册和启用的？\", \"top_k\": 5}"
```

---

## 第 5 步：接入 Claude Desktop（体验 MCP 工具调用）

1. 找到 Claude Desktop 配置文件：
   - macOS：`~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows：`%APPDATA%\Claude\claude_desktop_config.json`

2. 参考项目提供的模板 [`config/mcp/claude_desktop_config.json`](../config/mcp/claude_desktop_config.json)，把 `mcpServers.rag-mcp` 部分合并进去。**把 `command` 改成你虚拟环境的 python 完整路径**，例如：
   ```json
   {
     "mcpServers": {
       "rag-mcp": {
         "command": "C:/Users/你/.venv/Scripts/python.exe",
         "args": ["-m", "rag_mcp.mcp.server"]
       }
     }
   }
   ```

3. 完全退出并重启 Claude Desktop。

4. 在对话中直接提问，例如：
   - "帮我查一下知识库，RAG-MCP 项目的检索管线是怎么设计的？"
   - Claude 会自动调用 `knowledge_query` 工具，并返回带来源引用的回答。

> MCP 走 `stdio` 传输，与上面第 3-4 步的 REST 服务是**两个独立入口**，不需要同时运行。Claude Desktop 会自己拉起 MCP server 进程。

---

## 常见问题

**Q: 启动报 `ZHIPU_API_KEY` 未设置？**
A: `.env` 必须放在项目根目录（`RAG-MCP/`），且 Key 为真实值。Embedding 在服务启动时即初始化。

**Q: 摄入报文件不支持？**
A: 默认支持 `.txt` / `.md` / `.pdf` / `.html` / `.htm`（含 Confluence 导出 HTML），见 `config/settings.yaml` 中 `ingestion.supported_extensions`。

**Q: Claude Desktop 看不到 rag-mcp 工具？**
A: 检查 `command` 是否指向能 `import rag_mcp` 的 python（`pip install -e .` 是否执行过）；查看 Claude Desktop 的日志确认 MCP server 是否启动成功。

**Q: 想换向量库或加 Redis？**
A: 编辑 `config/settings.yaml`，完整配置项参考 `config/settings.yaml.example`。

---

## 下一步

- 浏览所有 REST 接口：[技术文档.md](技术文档.md) §6.1
- 了解 Skill 机制与 MCP 协议：[技术文档.md](技术文档.md) §5
- 运行检索评测：`curl -X POST http://127.0.0.1:8000/api/v1/evaluations/run`
- 开启 Dashboard 观测：`streamlit run backend/src/rag_mcp/observability/dashboard/app.py`
