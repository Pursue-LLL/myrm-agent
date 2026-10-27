"""ACP agent that stops reading its stdin once a session exists, like an agent hung in the middle of a task.

Run as a subprocess: python tests/toolkits/acp/_stalled_acp_agent.py <seconds> [<tool pid file>]
It answers ``initialize`` (advertising image prompts) and ``session/new``, then sleeps for ``<seconds>`` without
reading anything, so a large ``session/prompt`` written after that stays half written in the pipe.
With a ``<tool pid file>`` it first starts a tool process, like an agent running a long command, that inherits the
agent's stdin and stdout, and writes the tool's PID to that file.
Stdlib only: the framing is one JSON-RPC message per line.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time


def _send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def _start_tool(pid_file: str) -> None:
    tool = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    with open(pid_file, "w", encoding="utf-8") as handle:
        handle.write(str(tool.pid))


def main() -> None:
    stall_seconds = float(sys.argv[1])
    tool_pid_file = sys.argv[2] if len(sys.argv) > 2 else None
    for line in sys.stdin:
        request = json.loads(line)
        method = request.get("method")
        if method == "initialize":
            capabilities = {"promptCapabilities": {"image": True}}
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {"protocolVersion": 1, "agentCapabilities": capabilities},
                }
            )
        elif method == "session/new":
            if tool_pid_file is not None:
                _start_tool(tool_pid_file)
            _send({"jsonrpc": "2.0", "id": request["id"], "result": {"sessionId": "stalled-1"}})
            time.sleep(stall_seconds)
            return


if __name__ == "__main__":
    main()
