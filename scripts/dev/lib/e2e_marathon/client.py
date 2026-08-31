"""CLI client for the marathon supervisor."""

from __future__ import annotations

import json
import socket
import sys
import time

from e2e_marathon.paths import MarathonPaths, resolve_paths
from e2e_marathon.rpc_types import MarathonCommand, MarathonRpcResponse


def _read_response(sock: socket.socket, timeout_sec: float = 30.0) -> MarathonRpcResponse:
    sock.settimeout(timeout_sec)
    chunks: list[bytes] = []
    while True:
        block = sock.recv(65536)
        if not block:
            break
        chunks.append(block)
        if block.endswith(b"\n"):
            break
    raw = b"".join(chunks).strip()
    if not raw:
        return MarathonRpcResponse(ok=False, exit_code=1, stdout="", stderr="empty RPC response")
    data = json.loads(raw.decode("utf-8"))
    return MarathonRpcResponse(
        ok=bool(data.get("ok")),
        exit_code=int(data.get("exit_code", 1)),
        stdout=str(data.get("stdout", "")),
        stderr=str(data.get("stderr", "")),
        state=data.get("state") if isinstance(data.get("state"), dict) else None,
    )


def call_rpc(
    paths: MarathonPaths,
    command: MarathonCommand,
    timeout_sec: float = 30.0,
) -> MarathonRpcResponse:
    payload = json.dumps({"cmd": command}) + "\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_sec)
        sock.connect(str(paths.sock_file))
        sock.sendall(payload.encode("utf-8"))
        return _read_response(sock, timeout_sec=timeout_sec)


def ensure_daemon(paths: MarathonPaths) -> None:
    script = paths.agent_root / "scripts" / "dev" / "e2e-marathon-supervisor.sh"
    if not script.is_file():
        raise RuntimeError(f"Missing marathon launcher: {script}")
    import subprocess

    result = subprocess.run(
        ["bash", str(script), "start"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "marathon supervisor start failed")
    for _ in range(30):
        try:
            response = call_rpc(paths, "ping", timeout_sec=2.0)
            if response.ok:
                return
        except OSError:
            pass
        time.sleep(0.2)
    raise RuntimeError("Marathon supervisor start succeeded but ping failed")


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: e2e_marathon.client <start|status|shutdown|ping>", file=sys.stderr)
        return 1
    command = sys.argv[1]
    if command not in ("start", "status", "shutdown", "ping"):
        print(f"Unknown command: {command}", file=sys.stderr)
        return 1
    paths = resolve_paths()
    if command == "status" and not paths.sock_file.is_socket():
        print('{"running":false,"ledger":null}')
        return 0
    if command != "status":
        ensure_daemon(paths)
    response = call_rpc(paths, command)  # type: ignore[arg-type]
    if response.stdout:
        sys.stdout.write(response.stdout)
        if not response.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if response.stderr:
        sys.stderr.write(response.stderr)
        if not response.stderr.endswith("\n"):
            sys.stderr.write("\n")
    return response.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
