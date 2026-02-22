# RAG Engine — AutoAudit 知识库检索模块

**负责人：Student B** **模块路径：`/rag_engine/`**

------

本模块是 AutoAudit 系统的知识底座，负责为 LLM 提供历史漏洞攻击案例作为参考，解决"LLM 不知道怎么写 Foundry PoC"的问题。

工作流程：Student A 的 Auditor Node 分析完目标合约后，会把漏洞描述传进来，本模块从向量数据库里找出最相似的历史攻击案例（含完整 PoC 代码模板），返回给 LLM 作为 prompt 的一部分。有了真实案例参考，LLM 生成的 PoC 质量会显著提升，这也是我们要验证的 **假设 H1（RAG 增益）** 的核心。

知识库目前收录了 4 个真实 DeFi 攻击案例：

| 案例                 | 漏洞类型               |
| -------------------- | ---------------------- |
| EtherStore           | SWC-107 经典重入攻击   |
| Lendf.Me (2020)      | ERC777 Token Hook 重入 |
| PancakeBunny (2021)  | 闪电贷价格操纵         |
| Cream Finance (2021) | 闪电贷 + 重入组合攻击  |

------

## 文件结构

```
rag_engine/
├── data/                              # 4 个历史漏洞的 JSON 数据文件
│   ├── 001_etherstore_reentrancy.json
│   ├── 002_lendfme_reentrancy.json
│   ├── 003_pancakebunny_flashloan.json
│   └── 004_creamfinance_combo.json
├── chroma_db/                         # ChromaDB 持久化数据库（build_index 后自动生成）
├── __init__.py
├── indexer.py                         # 嵌入模型 + 入库核心逻辑（内部使用）
├── build_index.py                     # 一键建库脚本（首次使用前运行一次）
├── retriever.py                       # ⭐ 对外接口，Student A 调用这个
├── mock_retriever.py                  # Mock 版本，Student A 在真实版本完成前使用
└── eval_retrieval.py                  # 检索质量评估脚本（Demo Day 展示用）
```

------

## 快速开始

### 环境要求

```bash
# Python 3.11，激活 autoaudit conda 环境后安装
pip install chromadb sentence-transformers
```

### 第一步：建库（只需运行一次）

```bash
# 在项目根目录执行
python rag_engine/build_index.py
```

首次运行会自动从 HuggingFace 下载嵌入模型 `bge-small-en-v1.5`（约 130MB），需要联网，大约 2-5 分钟。下载完成后模型会缓存到本地，之后启动无需联网。

重建索引（修改了 data/ 文件后使用）：

```bash
python rag_engine/build_index.py --rebuild
```

### 第二步：调用检索接口

```python
from rag_engine.retriever import retrieve_similar_poc

results = retrieve_similar_poc(
    vulnerability_description="The contract sends Ether before updating balance, allowing reentrant withdrawal",
    top_k=2
)

for r in results:
    print(r["vuln_type"])        # 漏洞类型
    print(r["source_protocol"])  # 来源协议
    print(r["description"])      # 攻击原理描述
    print(r["poc_template"])     # 完整 Foundry PoC 代码模板
    print(r["similarity_score"]) # 相似度分数
```

### 返回值结构

```python
[
    {
        "vuln_type": "SWC-107-Reentrancy",
        "source_protocol": "EtherStore",
        "description": "EtherStore fails to update balance before external call...",
        "poc_template": "// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\n...",
        "similarity_score": 0.8021
    },
    ...
]
```

------

## 给 Student A：还没建库时用 Mock 版本

在你完成建库之前，可以直接用 mock 版本，接口签名完全一致，建好库后把导入路径换一行即可：

```python
# 开发阶段：用 mock
from rag_engine.mock_retriever import mock_retrieve_similar_poc as retrieve_similar_poc

# 联调阶段：换成真实版本（改这一行就够了）
from rag_engine.retriever import retrieve_similar_poc
```

------

## 验证检索质量（Demo Day 用）

```bash
python rag_engine/eval_retrieval.py
```

当前评估结果：

```
Recall@1（精准命中率）:  100%  ✅
误召回控制:              ✅ 通过
```

三类漏洞描述（重入 / ERC777 重入 / 闪电贷）均能精准命中对应案例，直接验证假设 H1 成立。

------

## 注意事项

- `chroma_db/` 目录已加入 `.gitignore`，不上传到仓库。团队成员 clone 代码后需要各自运行一次 `build_index.py` 在本地建库。
- Windows 用户运行时会看到符号链接相关的 Warning，可以忽略，不影响功能。
- `embeddings.position_ids UNEXPECTED` 这条提示也可以忽略，是模型加载时的已知信息，相似度计算完全正常。