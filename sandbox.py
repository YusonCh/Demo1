"""
Foundry 沙盒执行模块（sandbox.py）

目标：
- 封装 forge test 执行，提供确定性、可复现的执行环境；
- 使用 docker-py 启动一次性、隔离的容器运行不受信任的 PoC；
- 提供自愈循环接口：外部可基于编译/运行日志自动修复 PoC 后重试。

注意：
- 本模块只负责「安全执行 + 日志采集 + 错误解析」；
- 「如何根据错误日志修复 PoC」由上层 PoC 智能体 / LangGraph 节点实现；
- 通过 max_retries + repair_callback 即可形成最多 N 次的自愈循环。
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

try:
    import docker
    from docker.models.containers import Container
except Exception:  # pragma: no cover
    docker = None
    Container = object  # type: ignore


@dataclass
class SandboxConfig:
    image: str = "autoaudit-foundry-sandbox:latest"
    # Script passed to `bash -lc` inside the container.
    forge_command: str | Tuple[str, ...] = "cd /work && forge test -vv"
    timeout_seconds: int = 30
    mem_limit: str = "1g"
    nano_cpus: int = int(1e9)
    network_disabled: bool = True
    poc_filename: str = "Attack.t.sol"


@dataclass
class ExecutionResult:
    success: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    error_type: Optional[str] = None  # compile_error | test_fail | infra_error
    compiler_errors: Optional[str] = None
    test_summary: Optional[str] = None
    timed_out: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


class FoundrySandbox:
    def __init__(self, config: Optional[SandboxConfig] = None):
        self.config = config or SandboxConfig()
        if docker is None:
            raise RuntimeError(
                "docker SDK not installed. Run: pip install docker"
            )
        self._client = docker.from_env()
        try:
            self._client.ping()
        except Exception as e:  # pragma: no cover
            raise RuntimeError(
                "Cannot connect to Docker daemon. Start Docker Desktop (or dockerd)."
            ) from e

    def run_once(
        self, poc_source: str, target_contract_source: Optional[str] = None
    ) -> ExecutionResult:
        with self._prepare_workspace(
            poc_source, target_contract_source=target_contract_source
        ) as workdir:
            return self._run_in_container(workdir)

    def run_with_repair(
        self,
        initial_poc: str,
        target_contract_source: Optional[str] = None,
        max_retries: int = 5,
        repair_callback: Optional[Callable[[str, str, int], str]] = None,
    ) -> Tuple[ExecutionResult, Iterable[Dict]]:
        history = []
        current_poc = initial_poc
        result: Optional[ExecutionResult] = None

        for attempt in range(1, max_retries + 1):
            with self._prepare_workspace(
                current_poc, target_contract_source=target_contract_source
            ) as workdir:
                result = self._run_in_container(workdir)

            history.append(
                {
                    "attempt": attempt,
                    "poc": current_poc,
                    "result": result.to_dict(),
                }
            )

            if result.success:
                return result, history
            if repair_callback is None:
                break
            if result.timed_out or result.error_type == "infra_error":
                break

            logs = (result.stdout or "") + "\n" + (result.stderr or "")
            try:
                current_poc = repair_callback(current_poc, logs, attempt)
            except Exception as e:
                history.append({"attempt": attempt, "repair_error": str(e)})
                break

        if result is None:  # pragma: no cover
            result = ExecutionResult(
                success=False,
                exit_code=None,
                stdout="",
                stderr="No execution attempts were made.",
                error_type="infra_error",
                compiler_errors=None,
                test_summary=None,
                timed_out=False,
            )
        return result, history

    class _TempWorkspace:
        def __init__(self, path: Path):
            self.path = path

        def __enter__(self) -> Path:
            return self.path

        def __exit__(self, exc_type, exc, tb) -> None:
            try:
                shutil.rmtree(self.path, ignore_errors=True)
            except Exception:
                pass

    def _prepare_workspace(
        self, poc_source: str, target_contract_source: Optional[str]
    ) -> "_TempWorkspace":
        tmpdir = Path(tempfile.mkdtemp(prefix="autoaudit_foundry_"))
        (tmpdir / "src").mkdir(parents=True, exist_ok=True)
        (tmpdir / "test").mkdir(parents=True, exist_ok=True)

        if target_contract_source:
            (tmpdir / "src" / "Target.sol").write_text(
                target_contract_source, encoding="utf-8"
            )

        (tmpdir / "test" / self.config.poc_filename).write_text(
            poc_source, encoding="utf-8"
        )

        foundry_toml = tmpdir / "foundry.toml"
        foundry_toml.write_text(
            "[profile.default]\n"
            "src = 'src'\n"
            "test = 'test'\n"
            "libs = ['lib', '/opt/lib']\n"
            "solc_version = '0.8.23'\n"
            "optimizer = true\n"
            "optimizer_runs = 200\n",
            encoding="utf-8",
        )

        return self._TempWorkspace(tmpdir)

    def _run_in_container(self, workdir: Path) -> ExecutionResult:
        cfg = self.config
        stdout = ""
        stderr = ""
        exit_code: Optional[int] = None
        timed_out = False

        forge_command = cfg.forge_command
        if isinstance(forge_command, (tuple, list)):
            if (
                len(forge_command) >= 3
                and forge_command[0] == "bash"
                and forge_command[1] == "-lc"
            ):
                forge_command = str(forge_command[2])
            else:
                forge_command = " ".join(str(p) for p in forge_command)

        container: Optional[Container] = None
        try:
            container = self._client.containers.run(
                image=cfg.image,
                entrypoint=["bash"],
                command=["-lc", forge_command],
                volumes={str(workdir): {"bind": "/work", "mode": "rw"}},
                network_disabled=cfg.network_disabled,
                detach=True,
                mem_limit=cfg.mem_limit,
                nano_cpus=cfg.nano_cpus,
                security_opt=["no-new-privileges"],
                pids_limit=256,
                user="2000:2000",
                working_dir="/work",
                environment={"FOUNDRY_PROFILE": "default"},
            )
            wait_result = container.wait(timeout=cfg.timeout_seconds)
            if isinstance(wait_result, dict):
                exit_code = wait_result.get("StatusCode")
            else:
                exit_code = int(wait_result)
            logs = container.logs(stdout=True, stderr=True)
            stdout = (logs or b"").decode("utf-8", errors="replace")
            stderr = ""
        except Exception as e:
            timed_out = "timed out" in str(e).lower()
            stderr = f"Sandbox infra error: {e}"
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

        if timed_out:
            return ExecutionResult(
                success=False,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr or "forge test execution timed out.",
                error_type="infra_error",
                compiler_errors=None,
                test_summary=None,
                timed_out=True,
            )
        return self._post_process(stdout=stdout, stderr=stderr, exit_code=exit_code)

    def _post_process(
        self, stdout: str, stderr: str, exit_code: Optional[int]
    ) -> ExecutionResult:
        text = (stdout or "") + "\n" + (stderr or "")
        compile_patterns = [
            r"CompilerError:",
            r"Compilation failed",
            r"ParserError:",
            r"TypeError:",
            r"Error: Expected",
        ]
        is_compile_error = any(re.search(p, text) for p in compile_patterns)

        test_summary = None
        for pattern in (r"Tests:.*", r"Suite result:.*"):
            m = re.search(pattern, text)
            if m:
                test_summary = m.group(0).strip()
                break

        success = exit_code == 0 and not is_compile_error
        if is_compile_error:
            err_type = "compile_error"
            compiler_err = self._extract_compiler_errors(text)
        elif exit_code and exit_code != 0:
            err_type = "test_fail"
            compiler_err = None
        elif exit_code is None:
            err_type = "infra_error"
            compiler_err = None
        else:
            err_type = None
            compiler_err = None

        if test_summary is None and exit_code is not None:
            if exit_code == 0:
                test_summary = "forge test exited successfully (exit code 0)."
            else:
                test_summary = f"forge test failed (exit code {exit_code})."

        return ExecutionResult(
            success=success,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error_type=err_type,
            compiler_errors=compiler_err,
            test_summary=test_summary,
            timed_out=False,
        )

    @staticmethod
    def _extract_compiler_errors(text: str) -> str:
        lines = text.splitlines()
        important: list[str] = []
        for i, line in enumerate(lines):
            if "Error" in line or "CompilerError" in line or "ParserError" in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                important.extend(lines[start:end])
                important.append("----")
        return "\n".join(important).strip()


def main() -> None:
    import sys

    data_raw = sys.stdin.read()
    if not data_raw.strip():
        print(json.dumps({"error": "empty stdin"}))
        return

    try:
        req = json.loads(data_raw)
    except Exception as e:
        print(json.dumps({"error": f"invalid json: {e}"}))
        return

    action = req.get("action")
    if action != "run_forge_test":
        print(json.dumps({"error": f"unsupported action: {action}"}))
        return

    poc_source = req.get("poc_source") or ""
    max_retries = int(req.get("max_retries") or 1)

    try:
        sandbox = FoundrySandbox()
    except Exception as e:
        print(json.dumps({"error": f"init sandbox failed: {e}"}))
        return

    result, history = sandbox.run_with_repair(
        initial_poc=poc_source,
        max_retries=max_retries,
        repair_callback=None,
    )
    print(
        json.dumps(
            {"final_result": result.to_dict(), "history": list(history)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
