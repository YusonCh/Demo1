# AutoAudit-demo

AutoAudit-demo 是一个用于智能合约审计演示的 MVP 项目，包含：

- `RAG` 漏洞案例检索（`rag_engine/`）
- `Agent` 审计流程编排（`agent_graph/`）
- `Foundry + Docker` 沙箱执行 PoC（`sandbox.py`）
- `Streamlit` 可视化页面（`app.py`）

本文档目标是让组员可以快速上手、稳定运行、并按规范协作提交。

## 1. 快速开始（推荐）

### 1.1 环境要求

- Python `3.11+`（当前 `.venv` 使用 `3.13` 也可运行）
- Docker Desktop（必须已启动）
- 可访问 HuggingFace（首次会下载 embedding 模型）

### 1.2 安装依赖

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 1.3 启动 Web 界面

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502
```

浏览器打开：`http://localhost:8502`

说明：

- 如果 `8501` 被占用，直接改端口（如 `8502`、`8503`）。
- UI 支持不同运行模式（全链路 / 快速 mock / 仅静态分析）。

## 2. RAG 使用说明

### 2.1 重建索引

```powershell
.\.venv\Scripts\python.exe rag_engine/build_index.py --rebuild --batch-size 16
```

可选参数：

- `--rebuild`：强制全量重建
- `--batch-size`：embedding 批大小
- `--quiet`：只输出简要结果

### 2.2 评测检索质量与延迟

```powershell
.\.venv\Scripts\python.exe rag_engine/eval_retrieval.py
```

当前基线（最近一次）：

- Canonical Recall@1: `1.000`
- Paraphrase Recall@1: `1.000`
- Irrelevant avg score: `0.000`
- Warm avg latency: `~3-4ms`

## 3. Agent 与沙箱链路

### 3.1 命令行运行 Agent 图

```powershell
.\.venv\Scripts\python.exe -m agent_graph.graph
```

### 3.2 沙箱依赖

首次需要构建 Foundry 沙箱镜像：

```powershell
docker build -f Dockerfile.foundry-sandbox -t autoaudit-foundry-sandbox:latest .
```

`sandbox.py` 会通过 Docker 运行 `forge test`，并返回结构化执行结果（成功/失败/错误类型/摘要）。

## 4. 常用环境变量

### 4.1 LLM 相关

- `DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`
- `DEEPSEEK_API_BASE`（默认 `https://api.deepseek.com/v1`）
- `AUDIT_LLM_MODEL`（默认 `deepseek-chat`）

### 4.2 运行模式开关

- `USE_MOCK_RAG=1`：强制使用 mock 检索
- `USE_MOCK_LLM_FAST=1`：不调用线上 LLM，使用本地 deterministic PoC
- `SKIP_SANDBOX=1`：跳过沙箱执行

说明：Web 页面会按所选模式自动设置这些开关；CLI 调用时可手动设置。

## 5. 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前测试集覆盖：

- RAG 检索接口契约
- RAG 质量指标
- 索引构建增量/重建逻辑
- Windows 控制台评测脚本兼容性

## 6. 完整目录结构（参照 TechSpec v2）

```text
AutoAudit-demo/
├── agent_graph/                      # A: Agent 编排层（LangGraph）
│   ├── graph.py                      # 图定义与入口（run_audit / run_audit_stream）
│   ├── nodes.py                      # auditor/sandbox/report 节点实现
│   ├── prompts.py                    # LLM Prompt 模板
│   ├── state.py                      # 审计状态结构定义
│   └── __init__.py
├── rag_engine/                       # B: RAG 检索引擎
│   ├── data/                         # 漏洞样本语料（JSON，当前 24 条）
│   ├── chroma_db/                    # Chroma 持久化索引 + manifest（运行后生成）
│   ├── build_index.py                # 索引构建 CLI（支持 --rebuild/--batch-size/--quiet）
│   ├── eval_retrieval.py             # RAG 评测脚本（质量 + 延迟）
│   ├── indexer.py                    # 数据加载、增量索引、embedding 构建
│   ├── retriever.py                  # 对外检索接口（retrieve_similar_poc / warmup_retriever）
│   ├── mock_retriever.py             # Mock 检索实现（联调兜底）
│   ├── RAG Engine — AutoAudit 知识库检索模块.md
│   └── __init__.py
├── demo_contracts/                   # D: 演示合约输入
│   ├── VulnerableReentrancy.sol      # 漏洞版合约
│   └── SafeReentrancy.sol            # 安全版合约
├── tests/                            # 测试目录（单测 + 集成）
│   ├── test_integration.py
│   ├── test_sandbox.py
│   ├── test_rag_retriever_contract.py
│   ├── test_rag_quality.py
│   ├── test_rag_indexer.py
│   └── test_eval_script_windows_safe.py
├── agent_output/                     # Agent 本地运行产物（按轮次编号）
├── app.py                            # D: Streamlit 前端入口
├── sandbox.py                        # C: Foundry Docker 沙箱执行主模块
├── foundry_mcp_server.py             # Foundry 执行 MCP 适配入口
├── Dockerfile.foundry-sandbox        # Foundry 沙箱镜像构建文件
├── AutoAudit_Phase1_MVP_TechSpec_v2.md
├── requirements.txt
├── README.md
├── .gitignore
├── LICENSE
```

### 6.1 目录职责说明（按文件夹）

1. `agent_graph/`
- 系统工作流编排层，负责把「漏洞分析 → RAG 检索 → PoC 生成 → 沙箱执行 → 报告输出」串起来。
- 对应 TechSpec 的 Student A 模块。

2. `rag_engine/`
- 知识库与检索层，负责样本管理、向量索引构建、检索与评测。
- 对应 TechSpec 的 Student B 模块。

3. `rag_engine/data/`
- 漏洞语料源（JSON）。每条记录包含漏洞类型、协议、描述和 PoC 模板等信息。
- 修改后需要重建索引（`build_index.py --rebuild`）。

4. `rag_engine/chroma_db/`
- ChromaDB 本地索引持久化目录，由构建脚本生成，不建议手动修改。

5. `demo_contracts/`
- 前端 Demo 的标准输入集合：漏洞版与安全版。
- 对应 TechSpec 的 Student D 预置输入职责。

6. `tests/`
- 项目测试集合，覆盖 RAG 契约、质量、索引、Windows 兼容和沙箱/集成链路。
- 合并前建议全量跑通。

7. `agent_output/`
- CLI 调用 `agent_graph` 时生成的本地输出目录（报告与 PoC 文件）。

8. `.venv/`、`.pytest_cache/`、`__pycache__/`
- 本地环境或缓存目录，不属于业务代码，通常不提交到仓库。

### 6.2 与 TechSpec 目录差异说明（避免混淆）

- TechSpec 示例中 C 模块路径是 `/sandbox/executor.py` 和 `/sandbox/mock_executor.py`。
- 当前仓库将其整合为根目录单文件 `sandbox.py`，功能上仍对应同一职责（执行 PoC、解析日志、返回结构化结果）。
- 如果后续需要完全对齐 TechSpec 目录，可再做一次“文件拆分但接口不变”的重构。

## 7. 协作提交流程（避免影响他人分支）

不要直接推 `main/master`，统一走「个人分支 + PR」：

```powershell
git fetch origin
git switch main
git pull --ff-only origin main
git switch -c feat/your-topic
git add .
git commit -m "your message"
git push -u origin feat/your-topic
```

然后在 GitHub 发起 PR：

- `base` 选团队目标分支
- `compare` 选你的个人分支

## 8. 常见问题排查

1. `ModuleNotFoundError: chromadb`
- 原因：没用项目 `.venv` 解释器。
- 处理：确认使用 `.\.venv\Scripts\python.exe` 执行命令。

2. `Port 8501 is not available`
- 原因：端口占用。
- 处理：改端口，如 `--server.port 8502`。

3. `Cannot connect to Docker daemon`
- 原因：Docker Desktop 未启动或无权限。
- 处理：启动 Docker Desktop，确认 `docker ps` 正常。

4. RAG 报错提示索引不存在
- 原因：`rag_engine/chroma_db` 未构建。
- 处理：执行 `rag_engine/build_index.py --rebuild`。

## 9. 组内建议

- 提交前至少运行一次：
  - `python rag_engine/eval_retrieval.py`
  - `python -m pytest -q`
- 修改 `rag_engine/data/*.json` 后，务必重建索引并更新评测结果。
- PR 描述建议包含：
  - 改动范围
  - 指标变化（Recall/Latency）
  - 测试结果
