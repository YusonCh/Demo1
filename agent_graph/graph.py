"""
LangGraph 审计图定义：
- auditor: RAG + LLM 生成 PoC
- sandbox: 在 Docker 沙盒中运行 Foundry PoC（forge test）
- generate_report: 汇总 RAG + 沙盒执行结果

从项目根目录运行：python -m agent_graph.graph 或 python agent_graph/graph.py
"""

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from agent_graph.state import AuditState
from agent_graph.nodes import auditor_node, report_node, sandbox_node

try:
    from langgraph.graph import END, StateGraph
except ImportError:
    StateGraph = None
    END = None


_APP = None


def build_graph():
    """构建并编译图。若无 langgraph 则返回 None。"""
    if StateGraph is None:
        return None

    global _APP
    if _APP is not None:
        return _APP

    graph = StateGraph(AuditState)

    graph.add_node("auditor", auditor_node)
    graph.add_node("sandbox", sandbox_node)
    graph.add_node("generate_report", report_node)

    graph.set_entry_point("auditor")
    graph.add_edge("auditor", "sandbox")
    graph.add_edge("sandbox", "generate_report")
    graph.add_edge("generate_report", END)

    _APP = graph.compile()
    return _APP


def run_audit(contract_source: str) -> dict:
    """
    单次审计入口。可替换为 stream 供前端消费。
    """
    app = build_graph()
    if app is None:
        # 降级：无 langgraph 依赖时，按固定顺序执行三段节点，保证 demo 可跑通
        state: dict = {"contract_source": contract_source, "status_log": []}
        state.update(auditor_node(state))
        state.update(sandbox_node(state))
        state.update(report_node(state))
        return state

    initial: AuditState = {
        "contract_source": contract_source,
        "status_log": [],
    }
    result = app.invoke(initial)
    return result


def run_audit_stream(contract_source: str):
    """
    流式审计入口：按节点执行顺序持续返回最新状态，用于前端实时展示进度。
    """
    app = build_graph()
    if app is None:
        # 降级：无 langgraph 依赖时，手动依次调用三个节点并逐步 yield
        state: dict = {"contract_source": contract_source, "status_log": []}
        state.update(auditor_node(state))
        yield state
        state.update(sandbox_node(state))
        yield state
        state.update(report_node(state))
        yield state
        return

    initial: AuditState = {
        "contract_source": contract_source,
        "status_log": [],
    }
    # 使用 LangGraph 的 stream 接口，直接按状态流输出
    for s in app.stream(initial, stream_mode="values"):
        yield s


if __name__ == "__main__":
    import json
    # 本地快速测试（RAG + 生成 PoC，无沙盒）
    demo_contract = """
    contract VulnerableVault {
        mapping(address => uint256) public balances;
        function deposit() external payable { balances[msg.sender] += msg.value; }
        function withdraw() external {
            uint256 amt = balances[msg.sender];
            (bool ok,) = msg.sender.call{value: amt}("");
            require(ok);
            balances[msg.sender] = 0;
        }
    }
    """
    out = run_audit(demo_contract)

    # 输出到终端
    print("=== Status log ===")
    for entry in out.get("status_log") or []:
        print(f"  [{entry.get('node')}] {entry.get('message')}")

    report = out.get("final_report")
    if report:
        print("\n=== Final report ===")
        print("  vuln_hypothesis:", (report.get("vuln_hypothesis") or "")[:200])
        print("  rag_context_count:", report.get("rag_context_count"))
        poc = report.get("generated_poc") or ""
        print("  generated_poc (length):", len(poc), "chars")
        if poc:
            print("  generated_poc (preview):\n" + poc[:500] + ("..." if len(poc) > 500 else ""))

    # 输出到带序列号的子文件夹，避免多次测试覆盖
    base_out = Path(__file__).resolve().parent.parent / "agent_output"
    try:
        base_out.mkdir(parents=True, exist_ok=True)
        # 已有 001, 002, ... 则取最大+1，否则从 001 开始
        existing = [d.name for d in base_out.iterdir() if d.is_dir() and d.name.isdigit()]
        next_num = max([int(n) for n in existing], default=0) + 1
        run_id = f"{next_num:03d}"
        out_dir = base_out / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. 报告（不含 generated_poc 正文，仅注明 PoC 文件路径）
        report_dump = {
            "run_id": run_id,
            "status_log": out.get("status_log"),
            "final_report": {
                "vuln_hypothesis": report.get("vuln_hypothesis") if report else None,
                "rag_context_count": report.get("rag_context_count") if report else None,
                "poc_file": "Attack.t.sol",
            } if report else None,
        }
        report_path = out_dir / "report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_dump, f, ensure_ascii=False, indent=2)

        # 2. generated_poc 单独写入 .sol 文件
        poc_content = (report.get("generated_poc") or "") if report else ""
        poc_path = out_dir / "Attack.t.sol"
        with open(poc_path, "w", encoding="utf-8") as f:
            f.write(poc_content)

        print(f"\n>>> Output folder: {out_dir}  (run #{run_id})")
        print(f"    - report.json   (status_log + final_report)")
        print(f"    - Attack.t.sol  (generated_poc)")
    except Exception as e:
        print(f"\n>>> Could not write output: {e}")
