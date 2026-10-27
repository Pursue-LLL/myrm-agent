"""ACP agent that stops reading its stdin once a session exists, like an agent hung in the middle of a task.

Run as a subprocess: python tests/toolkits/acp/_stalled_acp_agent.py <seconds>
It answers ``initialize`` (advertising image prompts) and ``session/new``, then sleeps for ``<seconds>`` without
reading anything, so a large ``session/prompt`` written after that stays half written in the pipe.
Stdlib only: the framing is one JSON-RPC message per line.
"""

from __future__ import annotations

import json
import sys
import time


def _send(message: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def main() -> None:
    stall_seconds = float(sys.argv[1])
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
            _send({"jsonrpc": "2.0", "id": request["id"], "result": {"sessionId": "stalled-1"}})
            time.sleep(stall_seconds)
            return


if __name__ == "__main__":
    main()
