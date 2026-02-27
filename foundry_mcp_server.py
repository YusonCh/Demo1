"""
Foundry_Execution_Skill — MCP Server（简化版）

本文件实现一个基于 stdin/stdout 的最小 MCP 风格 Server，把
`sandbox.FoundrySandbox` 暴露为一个可被 Agent 调用的工具：

- 工具名：Foundry_Execution_Skill.run_forge_test
- 输入参数：
    - poc_source: str
    - max_retries: int (可选，默认 3)
- 输出：ExecutionResult + 自愈历史

说明：
- 这是一个**最小可用 demo 实现**，遵循「请求 JSON → 响应 JSON」模式；
- 真正对接 Model Context Protocol 时，可以基于官方 `mcp` Python SDK
  把这里的 `run_forge_test` 封装为 Tool Handler。
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict

from sandbox import FoundrySandbox


def run_forge_test(poc_source: str, max_retries: int = 3) -> Dict[str, Any]:
    """
    调用 FoundrySandbox 执行 PoC。

    这里不注入 repair_callback，自愈逻辑由上层 Agent 完成；
    max_retries>1 时仅用于观察多轮执行的稳定性。
    """
    sandbox = FoundrySandbox()
    result, history = sandbox.run_with_repair(
        initial_poc=poc_source,
        max_retries=max_retries,
        repair_callback=None,
    )
    return {
        "final_result": result.to_dict(),
        "history": list(history),
    }


def handle_request(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    极简 MCP 风格请求处理。

    请求格式示例：
    {
      "jsonrpc": "2.0",
      "id": "1",
      "method": "call_tool",
      "params": {
        "tool": "Foundry_Execution_Skill.run_forge_test",
        "arguments": {
          "poc_source": "...",
          "max_retries": 1
        }
      }
    }
    """
    method = req.get("method")
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": "pong"}

    if method == "list_tools":
        return {
            "jsonrpc": "2.0",
            "id": req.get("id"),
            "result": [
                {
                    "name": "Foundry_Execution_Skill.run_forge_test",
                    "description": "Run forge test inside Docker sandbox and return structured logs.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "poc_source": {"type": "string"},
                            "max_retries": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 5,
                                "default": 3,
                            },
                        },
                        "required": ["poc_source"],
                    },
                }
            ],
        }

    if method == "call_tool":
        params = req.get("params") or {}
        tool_name = params.get("tool")
        args = params.get("arguments") or {}
        if tool_name != "Foundry_Execution_Skill.run_forge_test":
            return {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"},
            }
        poc_source = args.get("poc_source") or ""
        max_retries = int(args.get("max_retries") or 3)
        try:
            out = run_forge_test(poc_source=poc_source, max_retries=max_retries)
            return {"jsonrpc": "2.0", "id": req.get("id"), "result": out}
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "error": {"code": -32000, "message": f"Sandbox error: {e}"},
            }

    return {
        "jsonrpc": "2.0",
        "id": req.get("id"),
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main() -> None:
    """
    以「长驻进程」方式运行时：
    - 从 stdin 按行读取 JSON-RPC 请求；
    - 每行输出一个 JSON-RPC 响应到 stdout。

    示例（单次调用，可在 shell 中测试）：

        echo '{"jsonrpc":"2.0","id":"1","method":"call_tool","params":{"tool":"Foundry_Execution_Skill.run_forge_test","arguments":{"poc_source":"// your PoC","max_retries":1}}}' \\
          | python foundry_mcp_server.py
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            print(json.dumps(resp, ensure_ascii=False), flush=True)
            continue
        resp = handle_request(req)
        print(json.dumps(resp, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

