"""
Agent 工作流状态定义：RAG + 生成 PoC + 沙盒执行 / 自愈循环。
"""

from typing import Optional, TypedDict


class AuditState(TypedDict, total=False):
    """LangGraph 图的状态 Schema。"""

    contract_source: str             # 用户输入的合约源码
    vuln_hypothesis: str             # Auditor 节点生成的漏洞假设描述
    rag_context: list                # RAG 返回的 PoC 模板列表
    generated_poc: str               # 当前迭代的 PoC 代码

    # 沙盒执行相关
    sandbox_result: dict             # 最近一次沙盒执行结果（ExecutionResult.to_dict）
    sandbox_history: list            # 全部尝试历史（可用于前端展示）
    retry_count: int                 # 自愈重试次数（上限由节点控制，例如 3~5）

    status_log: list                 # 各节点状态消息，供前端流式展示
    final_report: Optional[dict]     # 最终审计报告
