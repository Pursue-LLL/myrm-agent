"""Verify mux daemon stamps and respond to a lightweight tools/list probe.

[INPUT]
- CDMCP mux state dir stamps and Unix socket path

[OUTPUT]
- exit 0 when daemon-start stamp matches expected ms and mux responds quickly

[POS]
Attach-mode heal gate: stamp match alone is insufficient when upstream still uses 65s.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path


def _read_stamp(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _mux_tools_list_probe(socket_path: str, *, timeout_sec: float) -> bool:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout_sec
    try:
        sock.settimeout(max(0.5, timeout_sec))
        sock.connect(socket_path)
        sock.sendall(f"{payload}\n".encode("utf-8"))
        buffered = b""
        while time.monotonic() < deadline:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buffered += chunk
            if b"\n" in buffered:
                line = buffered.split(b"\n", maxsplit=1)[0].decode("utf-8", errors="replace")
                parsed = json.loads(line)
                if isinstance(parsed, dict) and "result" in parsed:
                    return True
                if isinstance(parsed, dict) and parsed.get("error"):
                    return False
        return False
    except (OSError, json.JSONDecodeError, TimeoutError):
        return False
    finally:
        sock.close()


def mux_timeout_effective(*, state_dir: Path, expected_ms: int, socket_path: str) -> bool:
    stamp = _read_stamp(state_dir / "request-timeout-ms")
    daemon_stamp = _read_stamp(state_dir / "request-timeout-ms-at-daemon-start")
    expected = str(expected_ms)
    if stamp != expected or daemon_stamp != expected:
        return False
    if not socket_path or not os.path.exists(socket_path):
        return False
    return _mux_tools_list_probe(socket_path, timeout_sec=8.0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe mux request timeout effectiveness.")
    parser.add_argument("--expected-ms", type=int, required=True)
    parser.add_argument("--state-dir", type=str, required=True)
    parser.add_argument("--socket", type=str, default=os.environ.get("CDMCP_MUX_SOCKET", ""))
    args = parser.parse_args()
    ok = mux_timeout_effective(
        state_dir=Path(args.state_dir),
        expected_ms=args.expected_ms,
        socket_path=args.socket.strip(),
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
