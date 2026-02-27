from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st

from agent_graph.graph import run_audit, run_audit_stream
from agent_graph.state import AuditState


PROJECT_ROOT = Path(__file__).resolve().parent
DEMO_DIR = PROJECT_ROOT / "demo_contracts"

VULN_DEMO = DEMO_DIR / "VulnerableReentrancy.sol"
SAFE_DEMO = DEMO_DIR / "SafeReentrancy.sol"


def _load_demo_contract(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _init_session_state() -> None:
    """初始化前端用到的 session state。"""
    if "contract_source" not in st.session_state:
        # 默认加载漏洞版 Demo 合约，若不存在则给出占位内容
        default_src = _load_demo_contract(VULN_DEMO) or "// 在此粘贴 Solidity 合约源码，或点击上方按钮加载 Demo 合约。"
        st.session_state["contract_source"] = default_src

    if "contract_input" not in st.session_state:
        st.session_state["contract_input"] = st.session_state.get("contract_source", "")


def main() -> None:
    st.set_page_config(
        page_title="AutoAudit MVP Demo",
        layout="wide",
    )
    st.title("AutoAudit MVP — 智能合约 PoC 审计演示")

    _init_session_state()

    col_left, col_right = st.columns([3, 2])

    # ---------------- 左侧：合约输入区 ----------------
    with col_left:
        st.subheader("📝 合约输入区")

        # 运行模式选择：直接在前端切换不同 Agent / Mock 组合
        mode = st.radio(
            "运行模式",
            [
                "🚀 全链路 Agent（真实 LLM + 真实 RAG + 沙盒）",
                "⚡ 快速 Mock Agent（本地 RAG + 本地 PoC + 沙盒）",
                "🧪 仅静态启发式分析（不跑 RAG/LLM/沙盒）",
            ],
            index=1,
            help=(
                "全链路：展示真实 Agent 能力，但延迟较高；"
                "快速 Mock：用于课堂 Demo，延迟较低；"
                "仅静态：只看启发式分析，不生成 PoC、不进沙盒。"
            ),
        )

        demo_cols = st.columns(2)
        with demo_cols[0]:
            if st.button("加载漏洞 Demo 合约"):
                src = _load_demo_contract(VULN_DEMO)
                if src:
                    st.session_state["contract_source"] = src
                    st.session_state["contract_input"] = src
        with demo_cols[1]:
            if st.button("加载安全 Demo 合约"):
                src = _load_demo_contract(SAFE_DEMO)
                if src:
                    st.session_state["contract_source"] = src
                    st.session_state["contract_input"] = src

        contract_source = st.text_area(
            "Solidity 合约源码",
            key="contract_input",
            height=380,
        )

        # 同步到通用字段，便于后续使用
        st.session_state["contract_source"] = contract_source

        run_clicked = st.button("▶ 开始审计", type="primary")

    # ---------------- 右侧：实时状态看板 ----------------
    with col_right:
        st.subheader("📡 实时状态看板")
        status_placeholder = st.empty()

    report_container = st.container()

    if run_clicked:
        import os
        import time

        contract_src = (st.session_state.get("contract_input") or "").strip()
        if not contract_src:
            st.warning("请先输入或加载一个 Solidity 合约。")
            return

        status_log: List[Dict] = []
        final_state: Optional[AuditState] = None
        total_elapsed: float = 0.0

        # 根据前端选择的运行模式设置后端环境变量（驱动不同 Agent / Mock 组合）
        if mode.startswith("🚀"):
            # 全链路：真实 RAG + 真实 LLM + 沙盒
            os.environ.pop("USE_MOCK_RAG", None)
            os.environ.pop("USE_MOCK_LLM_FAST", None)
            os.environ.pop("SKIP_SANDBOX", None)
        elif mode.startswith("⚡"):
            # 快速 Mock：本地 RAG + 本地 deterministic PoC + 沙盒
            os.environ["USE_MOCK_RAG"] = "1"
            os.environ["USE_MOCK_LLM_FAST"] = "1"
            os.environ.pop("SKIP_SANDBOX", None)
        else:
            # 仅静态启发式：不生成 PoC，不跑 RAG/LLM/沙盒
            os.environ["USE_MOCK_RAG"] = "1"
            os.environ["USE_MOCK_LLM_FAST"] = "1"
            os.environ["SKIP_SANDBOX"] = "1"

        with st.spinner("审计进行中，请稍候（目标 < 60 秒）..."):
            start_ts = time.perf_counter()
            try:
                # 使用流式接口，一边执行一边刷新状态看板和计时
                for state in run_audit_stream(contract_src):
                    status_log = state.get("status_log") or status_log
                    total_elapsed = time.perf_counter() - start_ts
                    final_state = state  # 不断覆盖，结束时即为最终状态

                    with status_placeholder.container():
                        st.write(f"当前审计用时：{total_elapsed:.1f} 秒")
                        if not status_log:
                            st.info("等待审计流程启动...")
                        else:
                            for entry in status_log:
                                node = entry.get("node", "?")
                                msg = entry.get("message", "")
                                st.write(f"[{node}] {msg}")
                # 兜底：若流中从未返回状态，则视为异常
                if final_state is None:
                    st.error("审计流程未返回任何状态，请检查后端日志。")
                    return
            except Exception as e:
                st.error(f"审计流程执行失败：{e}")
                return

        with report_container:
            st.subheader("📊 最终审计报告")

            if final_state is None:
                st.error("审计流程未返回任何结果，请检查终端日志。")
                return

            final_report = final_state.get("final_report")
            if not final_report:
                st.info("未生成最终报告，请查看上方状态日志（可能是沙盒基础设施未准备好）。")
                return

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("RAG 模板数量", final_report.get("rag_context_count", 0))
            with col2:
                st.metric(
                    "沙盒执行是否成功",
                    "✅ 成功" if final_report.get("sandbox_success") else "⚠️ 失败",
                )
            with col3:
                st.write(f"错误类型: {final_report.get('sandbox_error_type') or '-'}")
            with col4:
                st.metric("总用时（秒）", f"{total_elapsed:.1f}")

            with st.expander("漏洞分析与攻击路径", expanded=True):
                st.write(final_report.get("vuln_hypothesis") or "（暂无漏洞分析）")

            with st.expander("生成的 PoC 代码", expanded=False):
                poc_code = final_report.get("generated_poc") or ""
                if poc_code:
                    st.code(poc_code, language="solidity")
                else:
                    st.write("暂无 PoC 代码。")

            with st.expander("Foundry 执行摘要", expanded=False):
                summary = final_report.get("sandbox_test_summary")
                st.write(summary or "暂无执行摘要，请查看沙盒状态日志。")
    else:
        # 初始状态下给一个占位的报告区域，保持布局稳定
        with report_container:
            st.subheader("📊 最终审计报告")
            st.info("点击左侧「开始审计」按钮后，这里会展示最终报告摘要与 PoC 详情。")


if __name__ == "__main__":
    main()

