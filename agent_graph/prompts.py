"""
Agent 所用 Prompt 模板 — 集中管理便于调优。
"""

# 系统提示：Auditor 角色与输出格式
AUDITOR_SYSTEM = """You are a smart contract security auditor. Given a Solidity contract, you output a JSON object with:
- vuln_type: short label (e.g. SWC-107-Reentrancy)
- attack_mechanism: brief natural language description of the vulnerability and attack path
- poc_code: full Foundry test file content (Attack.t.sol), using forge-std/Test.sol, no explanation outside JSON.
Output only valid JSON, no markdown code block."""

# 人类消息：合约 + RAG 上下文
def auditor_user_prompt(contract_source: str, rag_context: list) -> str:
    poc_templates = "\n\n---\n\n".join(
        item.get("poc_template", "")[:2000] for item in rag_context
    )
    return f"""Analyze this contract and produce a vulnerability hypothesis and a Foundry PoC test.

Contract:
```
{contract_source[:8000]}
```

Reference PoC templates from similar past vulnerabilities (use as style/structure reference only):
{poc_templates[:4000] if poc_templates else "(none)"}

Output JSON: vuln_type, attack_mechanism, poc_code (full .t.sol content)."""


# 自愈：根据 stderr 修复 PoC
def self_heal_user_prompt(stderr: str) -> str:
    return f"""The following Foundry test file failed to compile. Fix the code and return ONLY the complete fixed Solidity file content, no explanation.

Compiler error:
```
{stderr[:3000]}
```"""
