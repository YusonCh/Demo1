# AutoAudit-demo 运行说明

当前仓库包含：
- **RAG 知识库（rag_engine）**
- **Agent 工作流（agent_graph）**
- **沙盒执行模块（sandbox.py + Dockerfile.foundry-sandbox）**

现在已支持完整的「RAG → 生成 PoC → 沙盒执行」闭环（前端 UI 仍由其他同学负责）。

---

## 一、环境要求

- **Python 3.11**（推荐用 conda 或 venv 隔离）
- **macOS / Ubuntu**（或 Windows + WSL2）

---

## 二、安装依赖

在项目根目录 `AutoAudit-demo/` 下执行：

```bash
cd /Users/Yuson/Desktop/test/BlockTest/AutoAudit-demo
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

首次运行会从 HuggingFace 下载嵌入模型 `bge-small-en-v1.5`（约 130MB），之后会使用本地缓存。

---

## 三、运行方式

### 1. 构建 RAG 知识库索引（必须先执行一次）

在项目根目录下执行（保证当前目录是 `AutoAudit-demo`，这样 `rag_engine` 才能被正确导入）：

```bash
cd /Users/Yuson/Desktop/test/BlockTest/AutoAudit-demo
python rag_engine/build_index.py
```

- 首次会读取 `rag_engine/data/*.json`，用 bge 模型做嵌入并写入 `rag_engine/chroma_db/`。
- 若索引已存在会跳过；强制重建可加 `--rebuild`：
  ```bash
  python rag_engine/build_index.py --rebuild
  ```

### 2. 运行检索质量评估（验证假设 H1）

Demo 日可直接用该脚本展示 RAG 检索效果：

```bash
cd /Users/Yuson/Desktop/test/BlockTest/AutoAudit-demo
python rag_engine/eval_retrieval.py
```

会跑多组查询（重入、闪电贷等），检查 Top-1 是否命中预期协议、无关查询相似度是否偏低。

### 3. 在代码中调用检索接口

```python
from rag_engine.retriever import retrieve_similar_poc

results = retrieve_similar_poc(
    "contract sends Ether before updating balance allowing reenter withdraw",
    top_k=2
)
for r in results:
    print(r["source_protocol"], r["similarity_score"], r["poc_template"][:200])
```

需在**已运行过 `build_index.py`** 且当前工作目录或 `sys.path` 包含项目根目录时使用。

### 4. 运行 Agent 工作流（RAG + 生成 PoC）

在项目根目录执行（无 API Key 时使用 mock retriever 的模板作为 PoC）：

```bash
cd /Users/Yuson/Desktop/test/BlockTest/AutoAudit-demo
python -m agent_graph.graph
```

使用真实 LLM 生成 PoC 时设置环境变量后再运行：

```bash
export DEEPSEEK_API_KEY="your-key"
python -m agent_graph.graph
```

---

## 四、目录结构（当前）

```
AutoAudit-demo/
├── AutoAudit_Phase1_MVP_TechSpec_v2.md   # 技术规格与分工
├── requirements.txt
├── README.md
├── docs/
│   └── GIT_AGENT_UPLOAD.md               # Agent 开发与 Git 上传步骤
├── agent_graph/                           # Agent 工作流（RAG + 生成 PoC，无沙盒）
│   ├── state.py, nodes.py, graph.py, prompts.py
├── sandbox.py                          # Foundry Docker 沙盒执行模块
├── foundry_mcp_server.py               # Foundry_Execution_Skill（简化 MCP Server）
├── Dockerfile.foundry-sandbox          # 沙盒容器镜像
└── rag_engine/
    ├── build_index.py      # 一键建库
    ├── eval_retrieval.py   # 检索质量评估
    ├── indexer.py          # 索引逻辑
    ├── retriever.py        # 检索接口
    ├── mock_retriever.py   # Mock 供 Agent 联调
    ├── data/               # 漏洞案例 JSON
    └── chroma_db/          # ChromaDB 持久化目录（运行后生成）
```

---

## 五、确定性沙盒隔离与自愈循环（工程实现概览）

- **隔离方式**：使用 `docker` SDK 调用 `autoaudit-foundry-sandbox:latest` 镜像，创建一次性容器：
  - 禁止网络（`network_disabled=True`）
  - 非 root 用户（`UID/GID = 1000:1000`，与 Dockerfile 中一致）
  - 限制资源（`mem_limit=1g`, `nano_cpus=1e9`, `pids_limit=256`, `no-new-privileges`）
  - 容器退出后立即 `remove(force=True)`，避免残留
- **确定性执行**：`sandbox.py` 在临时目录中构建最小 Foundry 工程：
  - 写入 `foundry.toml`，锁定 `solc_version=0.8.23` 与优化参数
  - 将 PoC 写入 `test/Attack.t.sol`
  - 通过 `forge test -vv` 执行，并采集 stdout/stderr
- **日志解析与错误分类**：`ExecutionResult` 结构化返回：
  - `success / exit_code / stdout / stderr / error_type / compiler_errors / test_summary / timed_out`
  - 使用正则从 Foundry 输出中提取 `CompilerError/ParserError/TypeError` 等关键信息，作为「Show, Don't Tell」风格的反馈给 PoC Agent。
- **自愈循环接口**：
  - `FoundrySandbox.run_with_repair(initial_poc, max_retries, repair_callback)`：
    - 每轮执行后将完整日志传给 `repair_callback(poc_src, logs, attempt)`；
    - 回调可由 LangGraph 中的 LLM 节点实现，用于自动修复语法/编译错误；
    - 最多重试 `max_retries` 次（建议 3–5 次），形成可控的自愈闭环。

LangGraph 侧在 `agent_graph/state.py` / `nodes.py` / `graph.py` 中已经集成了 `sandbox_node`，会在 `auditor_node` 生成 PoC 后自动调用沙盒执行，并将结果汇总到最终报告。

## 六、沙盒 Demo：从合约到确定性 PoC 执行

1. **准备 Foundry 沙盒镜像（一次性）**

```bash
cd /Users/Yuson/Desktop/test/BlockTest/AutoAudit-demo
docker build -f Dockerfile.foundry-sandbox -t autoaudit-foundry-sandbox:latest .
```

2. **运行完整审计闭环（RAG + PoC + 沙盒）**

```bash
cd /Users/Yuson/Desktop/test/BlockTest/AutoAudit-demo
python -m agent_graph.graph
```

控制台会输出：
- `status_log`：每个节点的状态（RAG、auditor、sandbox、report）
- `final_report`：包含 `sandbox_success` / `sandbox_error_type` / `sandbox_test_summary`

3. **直接调用沙盒模块（本地快速测试 PoC）**

```bash
python - << 'PY'
from pathlib import Path
from sandbox import FoundrySandbox

poc = """
// 这里填入 Attack.t.sol 内容
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;
import "forge-std/Test.sol";
contract T is Test {
    function testExploit() public {
        assertTrue(true);
    }
}
"""

sandbox = FoundrySandbox()
result = sandbox.run_once(poc)
print("success:", result.success)
print("error_type:", result.error_type)
print("test_summary:", result.test_summary)
PY
```

4. **以 Foundry_Execution_Skill（简化 MCP Server）方式调用**

```bash
echo '{"jsonrpc":"2.0","id":"1","method":"call_tool","params":{"tool":"Foundry_Execution_Skill.run_forge_test","arguments":{"poc_source":"// SPDX-License-Identifier: MIT\npragma solidity ^0.8.23;","max_retries":1}}}' \
  | python foundry_mcp_server.py
```

返回 JSON 中的 `final_result` 与 `history` 即为沙盒执行结果，可在 LangGraph 外部单独联调。
