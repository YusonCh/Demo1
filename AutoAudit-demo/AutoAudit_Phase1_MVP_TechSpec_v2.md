# 📄 AutoAudit 阶段一 (MVP Demo): 技术规格与并行开发分工说明书 v2.0

**阶段定位：Proof-of-Concept — 核心闭环验证 (Core Loop Validation)**
**目标里程碑：Progress Update 1（对应 Proposal 中 Apr 7 节点）**

**🔧 Student C — 沙盒执行引擎** 负责将 Solidity 代码在本地 Foundry 环境中跑起来。核心任务是实现 `execute_poc()` 函数：动态创建临时 Foundry 项目、调用 `forge test --json -vvv`、解析编译与运行日志并返回结构化结果。**第一天先交付 `mock_executor.py`**（硬编码模拟三种返回状态），给 A 用。本模块与其他人完全解耦，可从第一天独立开发，写完记得附三个集成测试用例（编译报错 / 执行成功 / 超时各一个）。

------

**🤖 Student A — Agent 工作流** 用 LangGraph 把整条审计链路串起来：RAG 检索 → LLM 生成 PoC → 沙盒执行 → 错误自愈循环。重点是把 `AuditState`（TypedDict）设计好，以及实现自愈节点的条件路由（编译失败就把 stderr 喂回 LLM，重试上限 3 次）。开发期间用 C 的 `mock_executor.py` 和自己写的 `mock_retriever` 驱动，不依赖任何人。流式状态输出需要对接 D 的前端，提前和 D 对齐数据格式。

------

**📚 Student B — RAG 知识库** 从 DeFiHackLabs 手动整理 4 个历史漏洞案例（重入 × 2、闪电贷 × 2），构建"自然语言描述 + PoC 代码模板"的文档对，用 `bge-small-en-v1.5` 本地嵌入后存入 ChromaDB。实现 `retrieve_similar_poc()` 接口。**重点**：写一个 `eval_retrieval.py` 验证检索质量（输入重入漏洞描述，Top-1 必须命中对应案例），这个结果直接用于 Demo 展示假设 H1 成立。**第一天先交付 `mock_retriever.py`**。

------

**🖥️ Student D — 前端集成与联调** 开发 Streamlit 双栏界面（左侧合约输入 + 右侧实时状态看板 + 底部报告区），并在 `/demo_contracts/` 准备好两个预置合约（漏洞版 + 安全版）供 Demo 使用。**核心职责不只是 UI**，A/B/C 模块合并后由你主导联调，跑通全链路冒烟测试，记录耗时（目标 < 60s），发现跨模块问题及时反馈。同时维护 `requirements.txt`，确保大家环境统一。

---

## 一、MVP 目标与验证假设 (Objectives & Hypotheses to Validate)

本阶段的工程价值不在于堆砌功能，而在于**对项目的两个核心学术假设进行可证伪的实证验证**：

> **假设 H1（RAG 增益假设）：** 为 LLM 提供历史 PoC 模板（RAG Context）后，其生成的 Foundry 测试脚本的一次性编译通过率，将显著高于无 RAG 的基准（Baseline）。
>
> **假设 H2（沙盒闭环假设）：** LLM 生成的 PoC 脚本在初次编译失败后，通过将 `stderr` 日志反馈给 LLM（Self-Healing），可以在 ≤3 次迭代内将编译错误自愈，并最终执行成功。

MVP Demo 的一切工程决策均服务于对上述两个假设的验证与展示。超出此范围的功能（如多 Agent 辩论、Slither AST 切片、Redis 语义缓存）均推迟至后续阶段。

---

## 二、系统架构总览 (MVP System Architecture)

MVP 采用单链路线性 Pipeline，而非 Proposal 中完整的多 Agent DAG，以最大化核心路径的可靠性：

```
[用户输入: 含漏洞的 Solidity 合约]
        │
        ▼
[Module B: RAG 检索引擎]
  └─ 向 ChromaDB 查询最相似的历史 PoC 模板
        │  返回: 相关漏洞代码片段 + 攻击模式描述
        ▼
[Module A: LangGraph 编排引擎 (Auditor Node)]
  └─ 构造 Prompt = 目标合约 + RAG Context
  └─ 调用 DeepSeek-Coder-V3 API → 生成 Attack.t.sol
        │
        ▼
[Module A: LangGraph 编排引擎 (Self-Healer Node)]  ◄──────┐
  └─ 调用 Module C 的 execute_poc() 接口                  │
        │                                              │
        ├── status: "compile_error" → 提取 stderr ─────┘
        │                             (retry ≤ 3次)
        │
        └── status: "success" ──────────────────────────►
                                                    [Module D: Streamlit UI]
                                                      └─ 展示执行报告 + 状态日志
```

**关键设计原则：**
- **接口先于实现。** 四人在第一天对齐所有 API Contract（见第四节），此后各自独立开发，互不阻塞。
- **Mock-First 并行。** 任何依赖下游模块的组件，均先用 Mock 函数驱动本地测试，待真实模块就绪后替换。
- **Demo 路径唯一化。** 只保证重入漏洞（Reentrancy / SWC-107）这一条路径跑通，不追求泛化性。

---

## 三、统一技术环境基线 (Unified Technical Baseline)

在首次团队会议中，全员必须对齐以下环境配置，**任何偏差均需在 GitHub Issue 中记录并经全体确认**：

| 组件 | 选型 | 说明 |
|------|------|------|
| **操作系统** | macOS (Apple Silicon) / Ubuntu 22.04 | Windows 用户强制使用 WSL2 (Ubuntu)，Foundry 在原生 Windows 下存在已知兼容性问题 |
| **Python** | 3.11（统一版本） | 使用 `conda` 或 `venv` 隔离，禁止使用系统 Python |
| **LLM API** | DeepSeek-Coder-V3（主力） | 兼容 `openai-python` SDK，仅修改 `base_url`。Token 成本约为 GPT-4o 的 1/20，PoC 代码生成能力顶级 |
| **LLM 备用** | DeepSeek-R1 | 当 Coder-V3 输出质量不稳定时切换，具备更强的推理链（Chain-of-Thought） |
| **Agent 编排** | LangGraph 0.2.x | 用于构建有状态的图工作流 |
| **沙盒执行** | Foundry（本地安装）| MVP 阶段使用本地 `forge` 直接执行，Docker 容器化隔离推迟至正式版。安装命令：`curl -L https://foundry.paradigm.xyz \| bash` |
| **向量数据库** | ChromaDB（内存模式） | 无需独立部署，Python 直接 `import chromadb`，极速启动 |
| **嵌入模型** | `BAAI/bge-small-en-v1.5`（本地推理）| HuggingFace 直接加载，无需 API Key，保证 Demo 可完全离线运行 |
| **前端框架** | Streamlit 1.35.x | |
| **代码仓库** | GitHub（私有仓库） | 分支策略见第五节 |

**依赖锁定：** Student D 负责在根目录维护 `requirements.txt`，所有人 `pip install -r requirements.txt` 后环境必须完全一致。

---

## 四、接口契约 (API Contracts) — 核心约束，不可更改

> ⚠️ **以下接口签名是四人协作的唯一契约。** 在第一次团队会议结束后即冻结，任何修改须经全体同意并在 GitHub 更新。

### 4.1 Module C → Module A：沙盒执行接口

```python
# 文件位置: /sandbox/executor.py

def execute_poc(target_contract_code: str, poc_code: str) -> dict:
    """
    将目标合约与攻击脚本写入临时 Foundry 项目并执行 forge test。

    Args:
        target_contract_code (str): 被审计的 Solidity 合约源码（字符串形式）
        poc_code (str): LLM 生成的 Foundry 攻击测试脚本（Attack.t.sol 内容）

    Returns:
        dict，严格遵循以下 JSON Schema，不得增减字段：
        {
            "status": "success" | "compile_error" | "runtime_error",
            "stdout": str,   # forge test 的完整标准输出（success 时非空，含 [PASS] 标记）
            "stderr": str,   # 编译器或运行时错误栈（error 时非空，直接用于喂给 LLM）
            "execution_time_ms": int  # 执行耗时，用于前端展示
        }

    异常处理:
        - 超时（>60s）：返回 {"status": "runtime_error", "stderr": "Execution timed out.", ...}
        - Foundry 未安装：抛出 RuntimeError，提示安装指引
    """
    pass
```

**Mock 版本（供 A 在 C 未完成前使用）：**

```python
# 文件位置: /sandbox/mock_executor.py
import random, time

def mock_execute_poc(target_contract_code: str, poc_code: str) -> dict:
    """
    模拟沙盒行为，用于 Student A 的本地 LangGraph 图测试。
    行为：首次调用以 60% 概率返回 compile_error，第二次调用返回 success。
    """
    # 通过外部变量控制重试次数以模拟自愈场景
    call_count = getattr(mock_execute_poc, '_call_count', 0) + 1
    mock_execute_poc._call_count = call_count
    time.sleep(0.5)  # 模拟执行延迟

    if call_count == 1 and random.random() < 0.6:
        return {
            "status": "compile_error",
            "stdout": "",
            "stderr": "Error (7789): Identifier not found or not unique: Attack\n --> test/Attack.t.sol:12:5",
            "execution_time_ms": 312
        }
    return {
        "status": "success",
        "stdout": "[PASS] testExploit() (gas: 142891)\nLogs:\n  Attacker balance before: 0\n  Attacker balance after: 10000000000000000000",
        "stderr": "",
        "execution_time_ms": 2840
    }
```

### 4.2 Module B → Module A：RAG 检索接口

```python
# 文件位置: /rag_engine/retriever.py

def retrieve_similar_poc(vulnerability_description: str, top_k: int = 2) -> list[dict]:
    """
    根据漏洞特征描述，从 ChromaDB 中检索最相关的历史 PoC 记录。

    Args:
        vulnerability_description (str): 对目标合约疑似漏洞的自然语言描述
                                        （由 Student A 的 Auditor Node 生成并传入）
        top_k (int): 返回记录数量，MVP 阶段固定为 2

    Returns:
        list of dict，每个 dict 结构如下：
        [
            {
                "vuln_type": str,        # 漏洞类型，如 "SWC-107-Reentrancy"
                "source_protocol": str,  # 来源协议名，如 "EtherStore (DeFiHackLabs)"
                "description": str,      # 该漏洞的自然语言攻击原理描述
                "poc_template": str,     # 完整的 Foundry PoC 代码模板（.t.sol 内容）
                "similarity_score": float  # ChromaDB 返回的相似度分数
            },
            ...
        ]
    """
    pass
```

---

## 五、并行开发任务分解 (Parallel Task Delegation)

### 👨‍💻 Student C：沙盒执行引擎工程师 (Sandbox Execution Engineer)

**独立性：** 此模块与其他三个模块完全解耦，可从第一天起独立开发与测试，无需等待任何人。

**工程目标：** 实现 `execute_poc()` 接口契约，将 LLM 生成的两段 Solidity 代码在本地 Foundry 环境中执行并返回结构化日志。

**详细任务拆解：**

1. **动态 Foundry 项目构建器**
   - 使用 Python `tempfile.mkdtemp()` 在系统临时目录创建符合 Foundry 规范的项目结构：
     ```
     /tmp/autoaudit_XXXXXX/
     ├── foundry.toml          # 基础配置，锁定 solc 版本为 0.8.20
     ├── src/
     │   └── Target.sol        # 写入 target_contract_code
     └── test/
         └── Attack.t.sol      # 写入 poc_code
     ```
   - `foundry.toml` 的基础模板需提前与团队对齐（尤其是 `src` 路径配置），避免集成时的路径错误。

2. **子进程管理与超时控制**
   - 使用 `subprocess.run(["forge", "test", "--json", "-vvv"], capture_output=True, timeout=60, text=True)` 执行编译与测试。
   - `--json` flag 使输出结构化，`-vvv` 使 `console.log` 输出在 stdout 中可见（用于展示"资金被盗取"的日志）。

3. **日志解析器 (Log Parser)**
   - **编译错误识别：** 检测 `returncode != 0` 且 `stderr` 包含 `Error` 关键字，提取从 `Error (` 开头到下一个空行的完整错误栈。注意过滤 ANSI 转义码（使用 `re.sub(r'\x1B\[[0-9;]*m', '', text)`）。
   - **运行时失败识别：** `returncode != 0` 但 `stderr` 不含编译错误，通常为 `FAIL` assertion，返回 `runtime_error`。
   - **成功识别：** `returncode == 0` 且 stdout 中包含 `[PASS]`，提取含 `Logs:` 部分的完整输出。

4. **资源清理**
   - 使用 `try...finally` 块确保执行后立即调用 `shutil.rmtree(tmp_dir)` 删除临时目录，防止磁盘泄漏。

5. **本地单元测试**
   - 在 `/sandbox/tests/` 目录中编写至少 3 个集成测试用例：
     - `test_compile_error.py`：传入故意遗漏 `import` 语句的 PoC，验证返回 `compile_error`。
     - `test_runtime_success.py`：传入标准的重入攻击 PoC（从 DeFiHackLabs 取样），验证返回 `success` 且 stdout 含 `[PASS]`。
     - `test_timeout.py`：传入包含无限循环的合约，验证 60s 后返回超时错误。
   - **测试通过是提交代码的前提条件（PR 门控）。**

**关键输出物：**
- `/sandbox/executor.py`（实现 `execute_poc`）
- `/sandbox/mock_executor.py`（供 A 使用，第一天即交付）
- `/sandbox/tests/`（单元测试套件）
- `/sandbox/README.md`（本地 Foundry 安装验证步骤）

---

### 👨‍💻 Student A：Agent 工作流架构师 (Agentic Workflow Architect)

**独立性：** 使用 `mock_execute_poc` 和 `mock_retrieve_similar_poc`（自行编写）驱动开发，与 B、C 完全解耦。

**工程目标：** 使用 LangGraph 构建审计状态机，实现"分析 → RAG 增强 PoC 生成 → 沙盒执行 → 错误自愈"的完整闭环，并暴露流式状态供 D 的前端消费。

**详细任务拆解：**

1. **状态模式定义 (State Schema)**

   ```python
   # /agent_graph/state.py
   from typing import TypedDict, Optional

   class AuditState(TypedDict):
       contract_source: str           # 原始合约代码
       vuln_hypothesis: str           # Auditor Node 生成的漏洞假设描述
       rag_context: list[dict]        # B 返回的 PoC 模板列表
       generated_poc: str             # 当前迭代的 PoC 代码
       sandbox_result: dict           # C 返回的执行结果
       retry_count: int               # 自愈重试次数（上限 3）
       status_log: list[str]          # 各节点的状态消息（用于前端流式展示）
       final_report: Optional[dict]   # 最终输出报告
   ```

2. **节点实现 (Node Implementation)**

   - **`auditor_node`（分析节点）：**
     - 使用 `langchain_openai.ChatOpenAI`，配置 `base_url` 指向 DeepSeek API endpoint。
     - Prompt 结构：系统提示（角色定义 + 输出格式约束）+ 人类消息（合约代码）。
     - 要求 LLM 以 JSON 格式输出：`{"vuln_type": ..., "attack_mechanism": ..., "poc_code": ...}`。
     - 使用 `langchain_core.output_parsers.JsonOutputParser` 解析，处理格式异常（若解析失败则重试一次）。
     - 触发 RAG：调用 `retrieve_similar_poc(state["vuln_hypothesis"])` 并将结果注入第二轮 Prompt。

   - **`self_healer_node`（自愈节点）：**
     - 调用 `execute_poc(state["contract_source"], state["generated_poc"])`。
     - 根据返回的 `status` 执行路由逻辑（见下方路由器）。
     - 若 `compile_error`：构造修复 Prompt（"以下 Foundry 测试脚本编译失败，错误信息如下：{stderr}，请修复代码并只返回完整的修复后代码，不要任何解释"），调用 LLM 获取修复版本，更新 `state["generated_poc"]`，`retry_count += 1`。

3. **条件路由器 (Conditional Router)**

   ```python
   def route_after_sandbox(state: AuditState) -> str:
       result = state["sandbox_result"]
       if result["status"] == "success":
           return "generate_report"
       if state["retry_count"] >= 3:
           return "generate_report"  # 超限，以失败状态生成报告
       return "self_healer"  # 继续修复循环
   ```

4. **流式状态推送**
   - 使用 LangGraph 的 `.stream()` 方法，在每个节点执行完毕后向外推送 `status_log` 的最新条目，格式为 `{"node": "auditor", "message": "...", "timestamp": ...}`，供 D 的前端实时消费。

5. **本地图测试**
   - 使用 `mock_execute_poc` 和 `mock_retrieve_similar_poc` 编写端到端的图执行测试，验证自愈循环在三次内收敛，以及超限后正确路由到报告生成节点。
   - 使用 `langgraph`  的 `draw_mermaid_png()` 生成 DAG 可视化图，用于 Demo 展示。

**关键输出物：**
- `/agent_graph/state.py`
- `/agent_graph/nodes.py`（各节点函数）
- `/agent_graph/graph.py`（图定义与编译 `app = graph.compile()`）
- `/agent_graph/prompts.py`（所有 Prompt 模板，集中管理便于调优）

---

### 👨‍💻 Student B：RAG 数据与检索工程师 (RAG Pipeline Engineer)

**独立性：** 输出物为标准 Python 函数，A 可用 Mock 版本先行开发，B 完成后直接替换。

**工程目标：** 构建 MVP 知识库，使系统能够为重入漏洞（Reentrancy）和闪电贷攻击（Flashloan）提供高质量的历史 PoC 模板检索，验证 H1 假设（RAG 增益）。

**详细任务拆解：**

1. **数据集构建（Mini-Corpus，MVP 专用）**

   从 [DeFiHackLabs](https://github.com/SunWeb3Sec/DeFiHackLabs) 手动筛选以下 **4 个** 历史案例（兼顾多样性）：
   
   | 案例 | 漏洞类型 | 选取理由 |
   |------|----------|----------|
   | `EtherStore` | SWC-107 Reentrancy | 教科书级别重入漏洞，作为 Demo 的主演示路径 |
   | `Lendf.Me (2020)` | ERC777 Reentrancy | 真实 DeFi 协议的重入变种，验证 RAG 泛化能力 |
   | `PancakeBunny (2021)` | Flashloan Price Manipulation | 闪电贷攻击典型案例 |
   | `Cream Finance (2021)` | Flashloan Re-entrancy Combo | 复合型攻击，作为压力测试数据 |

   每个案例构建一个 **"Code-NL Pair"** 文档，包含：
   - `vuln_type`、`protocol_name`、`attack_date`（元数据，用于 ChromaDB `where` 过滤）
   - `description`：攻击原理的自然语言描述（约 200 字）
   - `poc_template`：从 DeFiHackLabs 提取并清洗的完整 `.t.sol` 文件

2. **嵌入与索引管道 (Embedding & Indexing Pipeline)**

   ```python
   # /rag_engine/indexer.py
   from sentence_transformers import SentenceTransformer
   import chromadb

   # 使用本地 bge-small-en-v1.5，无需 API Key，首次运行自动下载
   model = SentenceTransformer("BAAI/bge-small-en-v1.5")
   
   # 重要：嵌入的文本必须是 description 字段，而非 poc_template 代码本身
   # 理由：自然语言描述的语义相似度计算比代码符号更稳定
   # poc_template 作为 metadata 存储，检索命中后直接返回给 LLM
   ```

   - ChromaDB 使用持久化模式（`chromadb.PersistentClient(path="./chroma_db")`），避免每次启动重新索引。
   - 提供 `/rag_engine/build_index.py` 脚本，执行一次后即可。

3. **检索函数实现**
   - 实现第四节中定义的 `retrieve_similar_poc()` 接口。
   - 使用 `collection.query(query_embeddings=[...], n_results=top_k)` 执行检索。
   - **必须处理边界情况：** 若 ChromaDB 尚未初始化（首次运行），应给出清晰的错误提示（"请先运行 build_index.py"）。

4. **检索质量验证（关键！用于证明 H1 假设）**
   - 编写 `/rag_engine/eval_retrieval.py`：
     - 对 4 个已索引案例，分别用其漏洞描述查询，验证 Top-1 返回的是否就是自身（Recall@1 = 1.0）。
     - 用未见过的漏洞描述（如"整数溢出导致余额被任意铸造"）查询，验证返回内容无关联（相似度分数 < 0.5），证明系统不会乱召回。
   - 此评估报告将直接用于 Progress Update 1 的汇报材料。

5. **Mock 版本（供 A 使用，第一天交付）**

   ```python
   # /rag_engine/mock_retriever.py
   def mock_retrieve_similar_poc(vulnerability_description: str, top_k: int = 2) -> list[dict]:
       """返回硬编码的重入漏洞 PoC 模板，供 Student A 测试 LangGraph 图"""
       return [
           {
               "vuln_type": "SWC-107-Reentrancy",
               "source_protocol": "EtherStore (Mock)",
               "description": "Attacker exploits missing state update before external call...",
               "poc_template": "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\nimport 'forge-std/Test.sol';\n// ... [hardcoded template]",
               "similarity_score": 0.92
           }
       ]
   ```

**关键输出物：**
- `/rag_engine/data/`（4 个 Code-NL Pair JSON 文件）
- `/rag_engine/indexer.py` & `build_index.py`
- `/rag_engine/retriever.py`（实现 `retrieve_similar_poc`）
- `/rag_engine/mock_retriever.py`（第一天交付）
- `/rag_engine/eval_retrieval.py`（检索质量评估脚本）

---

### 👨‍💻 Student D：全栈集成与演示负责人 (Integration & Demo Lead)

**核心定位：** 不仅是 UI 开发者，更是**系统集成测试的把关人**。当 A、B、C 的模块合并时，由 D 主导联调，发现并推动修复跨模块接口问题。

**详细任务拆解：**

1. **Streamlit 前端开发**

   **界面布局（双栏 + 底部报告区）：**
   ```
   ┌─────────────────────┬──────────────────────────┐
   │  📝 合约输入区       │  📡 实时状态看板           │
   │                     │  ┌─────────────────────┐  │
   │  [Solidity 代码框]  │  │ 🔍 检索 RAG 库...    │  │
   │                     │  │ 🤖 LLM 生成 PoC...   │  │
   │  [▶ 开始审计 按钮]  │  │ 🔨 沙盒编译中...     │  │
   │                     │  │ ⚠️ 编译失败，自愈中   │  │
   │                     │  │ ✅ 执行成功！         │  │
   │                     │  └─────────────────────┘  │
   └─────────────────────┴──────────────────────────┘
   ┌─────────────────────────────────────────────────┐
   │  📊 最终审计报告                                  │
   │  漏洞类型 | 攻击路径 | PoC 代码 | 执行日志        │
   └─────────────────────────────────────────────────┘
   ```

   **关键 UI 细节：**
   - 使用 `st.code(language="solidity")` 展示合约代码，启用语法高亮。
   - 实时状态看板使用 `st.status()` 或 `st.empty()` + 轮询 `app.stream()` 实现流式更新，每个节点完成后追加一行状态消息。
   - 自愈循环触发时，用 `st.warning("🔄 第 N 次自愈：编译错误已反馈给 LLM...")` 实时提示。
   - 最终报告使用 `st.expander` 分区折叠展示：① 漏洞分析，② 生成的 PoC 代码，③ Foundry 执行日志（含"资金被盗取"的 console.log 输出）。

2. **预置 Demo 合约**
   - 在 `/demo_contracts/` 目录中提供**两个**预置合约文件：
     - `VulnerableReentrancy.sol`：标准的重入漏洞合约（参考 DeFiHackLabs 的 EtherStore），作为 Demo Day 的主演示素材。
     - `SafeReentrancy.sol`：添加了 `nonReentrant` 修饰符的安全版本，用于对比展示系统**不会**误报（False Positive）。
   - UI 中提供 "Load Demo Contract" 一键填充按钮，避免 Demo 时手动粘贴代码出错。

3. **集成测试与联调 (Integration Testing)**
   - 当 A、B、C 分支合并后，D 负责执行**全链路冒烟测试**（Smoke Test）：
     - 传入 `VulnerableReentrancy.sol`，验证系统最终输出 `success` 报告。
     - 记录全链路端到端耗时，目标 < 60s（用于 Demo Day 控制节奏）。
   - 使用 GitHub Issues 追踪集成过程中发现的跨模块 Bug，明确指派修复责任人。

4. **`requirements.txt` 维护**
   - 作为依赖管理的唯一负责人，在集成时确保所有依赖版本锁定（使用 `pip freeze > requirements.txt`）。

**关键输出物：**
- `/app.py`（主 Streamlit 应用）
- `/demo_contracts/`（预置演示合约）
- `/tests/test_integration.py`（端到端冒烟测试脚本）
- `requirements.txt`（锁定版本）

---

## 六、仓库结构与 Git 工作流 (Repository Structure & Git Workflow)

```
autoaudit-mvp/
├── sandbox/                    # Student C
│   ├── executor.py
│   ├── mock_executor.py
│   └── tests/
├── rag_engine/                 # Student B
│   ├── data/
│   ├── indexer.py
│   ├── build_index.py
│   ├── retriever.py
│   ├── mock_retriever.py
│   └── eval_retrieval.py
├── agent_graph/                # Student A
│   ├── state.py
│   ├── nodes.py
│   ├── graph.py
│   └── prompts.py
├── demo_contracts/             # Student D
│   ├── VulnerableReentrancy.sol
│   └── SafeReentrancy.sol
├── tests/                      # Student D（集成测试）
│   └── test_integration.py
├── app.py                      # Student D
├── requirements.txt            # Student D 维护
├── .env.example                # API Key 模板（不提交真实 Key）
└── README.md                   # 环境搭建与运行指引
```

**分支策略：**

| 分支 | 负责人 | 说明 |
|------|--------|------|
| `main` | 全体 | 受保护，只接受 PR 合并 |
| `feature/sandbox` | C | 沙盒模块开发 |
| `feature/rag` | B | RAG 引擎开发 |
| `feature/agent` | A | Agent 工作流开发 |
| `feature/ui` | D | 前端与集成 |

**PR 规范：**
- 每个 PR 合并前，**必须**通过本模块的单元测试。
- PR 描述中附上本地测试截图。
- 所有 Mock 文件提交在 PR 最开始（T+1 天），其余实现随后提交。

---

## 七、Demo Day 执行脚本 (Demo Script for Progress Update 1)

> 目的：在 5 分钟内清晰地向导师展示两个假设（H1、H2）均有工程支撑。

**演示步骤（预计 5 分钟）：**

1. **（30s）背景介绍：** 展示 LangGraph DAG 可视化图，说明系统三个核心模块。

2. **（60s）验证 H1（RAG 增益）：** 不启动完整系统，直接在终端运行 `eval_retrieval.py`，现场展示 "Reentrancy 漏洞描述" 能在 ChromaDB 中精准召回 EtherStore PoC 模板（相似度 > 0.9）。

3. **（120s）核心闭环 Demo：** 在 Streamlit UI 中点击 "Load Demo Contract"，再点击 "开始审计"。**旁白提示观众关注状态看板**：`🔍 RAG 检索完毕 → 🤖 PoC 代码已生成 → ⚠️ 编译失败，触发自愈（第1次）→ ✅ 自愈成功，沙盒执行通过`。

4. **（60s）验证 H2（自愈闭环）：** 展开报告中的"执行日志"，高亮 Foundry 输出的 `[PASS] testExploit()` 和 `Attacker balance after: 10 ETH`，证明漏洞被确定性验证。

5. **（30s）展示 False Positive 抑制：** 传入 `SafeReentrancy.sol`，系统最终报告应显示"未能成功执行 PoC，漏洞未经验证确认"，说明系统不会乱报警。

---

## 八、风险与缓解策略 (Risk Register)

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|----------|
| Foundry 在某成员环境下安装失败 | 中 | 高 | C 在 `/sandbox/README.md` 提供完整排错指引；Foundry 官方支持 macOS/Linux/WSL2，问题可在 1 小时内解决 |
| DeepSeek API 不稳定 / 限速 | 低 | 高 | A 在 `graph.py` 中实现指数退避重试（最多 3 次）；备用切换 DeepSeek-R1 |
| LLM 生成 PoC 质量差，3 次自愈仍失败 | 中 | 中 | 这本身是一个**有效的实验数据点**（证明自愈有上限），在 Demo 中如实呈现。同时 B 提供高质量 RAG 模板来提升基准 |
| 集成时接口契约不一致 | 低 | 高 | 接口契约在第一天冻结并写入 `README.md`；所有 Mock 函数严格遵循相同签名 |
| Streamlit 流式更新卡顿 | 低 | 低 | D 提前测试 `st.empty()` 的刷新频率；若不稳定降级为轮询模式 |
