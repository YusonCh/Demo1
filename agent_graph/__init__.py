"""
Agent 工作流：RAG → LLM 生成 PoC → 沙盒执行 → 自愈循环。
build_graph / run_audit 延迟导入，避免 python -m agent_graph.graph 时的 RuntimeWarning。
"""

from agent_graph.state import AuditState


def build_graph():
    from agent_graph.graph import build_graph as _build_graph
    return _build_graph()


def run_audit(contract_source: str):
    from agent_graph.graph import run_audit as _run_audit
    return _run_audit(contract_source)


__all__ = ["AuditState", "build_graph", "run_audit"]
