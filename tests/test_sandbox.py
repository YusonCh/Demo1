from pathlib import Path

from sandbox import FoundrySandbox, SandboxConfig


class _DummyContainer:
    def wait(self, timeout=None):
        return {"StatusCode": 0}

    def logs(self, stdout=True, stderr=True):
        return b"Suite result: ok. 1 passed; 0 failed; 0 skipped; finished in 1.23ms"

    def remove(self, force=True):
        return None


class _DummyContainers:
    def __init__(self):
        self.run_kwargs = None

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        return _DummyContainer()


class _DummyClient:
    def __init__(self):
        self.containers = _DummyContainers()


def test_run_in_container_uses_bash_entrypoint_and_extracts_suite_summary():
    sandbox = FoundrySandbox.__new__(FoundrySandbox)
    sandbox.config = SandboxConfig(forge_command=("bash", "-lc", "echo hello"))
    sandbox._client = _DummyClient()

    result = sandbox._run_in_container(Path("."))
    run_kwargs = sandbox._client.containers.run_kwargs

    assert run_kwargs is not None
    assert run_kwargs["entrypoint"] == ["bash"]
    assert run_kwargs["command"] == ["-lc", "echo hello"]
    assert result.success is True
    assert result.test_summary is not None
    assert result.test_summary.startswith("Suite result:")


def test_post_process_has_summary_fallback_when_logs_are_empty():
    sandbox = FoundrySandbox.__new__(FoundrySandbox)
    result = sandbox._post_process(stdout="", stderr="", exit_code=0)
    assert result.success is True
    assert result.test_summary == "forge test exited successfully (exit code 0)."
