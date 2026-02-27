from pathlib import Path

from agent_graph.graph import run_audit


def test_integration_with_vulnerable_contract(monkeypatch):
    """
    冒烟测试：使用漏洞合约 + Mock 沙盒，验证 Agent 流程能跑通并返回报告。
    """
    # 使用 monkeypatch 将 sandbox.FoundrySandbox 替换为快速的假实现，
    # 避免在 CI 或本地必须依赖 Docker daemon。
    import sandbox as sandbox_mod
    from sandbox import ExecutionResult

    class DummySandbox:
        def __init__(self, *args, **kwargs):
            pass

        def run_once(self, poc_source: str, target_contract_source: str | None = None) -> ExecutionResult:
            return ExecutionResult(
                success=True,
                exit_code=0,
                stdout="[PASS] testExploit() (gas: 123456)\nLogs:\n  Attacker balance after: 10 ETH",
                stderr="",
                error_type=None,
                compiler_errors=None,
                test_summary="Tests: 1 passed, 0 failed",
                timed_out=False,
            )

    monkeypatch.setattr(sandbox_mod, "FoundrySandbox", DummySandbox)

    contract_path = Path("demo_contracts") / "VulnerableReentrancy.sol"
    assert contract_path.exists(), "Demo 合约缺失：demo_contracts/VulnerableReentrancy.sol"

    contract_source = contract_path.read_text(encoding="utf-8")
    result = run_audit(contract_source)

    final_report = result.get("final_report")
    assert final_report is not None, "final_report 不应为 None"

    # 确保报告中含有沙盒执行结果摘要
    assert final_report.get("sandbox_success") is True
    assert "Tests:" in (final_report.get("sandbox_test_summary") or "")

