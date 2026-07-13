"""Unix-socket RPC client for the dev stack supervisor."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from stack_supervisor.paths import StackPaths, resolve_paths
from stack_supervisor.rpc_types import RpcCommand, RpcResponse


def _sock_path(paths: StackPaths) -> str:
    return str(paths.supervisor_sock)


def _connect(paths: StackPaths, timeout_sec: float = 3.0) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout_sec)
    sock.connect(_sock_path(paths))
    return sock


def _read_response(sock: socket.socket, timeout_sec: float = 600.0) -> RpcResponse:
    sock.settimeout(timeout_sec)
    chunks: list[bytes] = []
    while True:
        try:
            block = sock.recv(65536)
        except socket.timeout:
            break
        if not block:
            break
        chunks.append(block)
        if block.endswith(b"\n"):
            break
    raw = b"".join(chunks).strip()
    if not raw:
        return RpcResponse(ok=False, exit_code=1, stdout="", stderr="empty RPC response")
    data = json.loads(raw.decode("utf-8"))
    return RpcResponse(
        ok=bool(data.get("ok")),
        exit_code=int(data.get("exit_code", 1)),
        stdout=str(data.get("stdout", "")),
        stderr=str(data.get("stderr", "")),
        state=data.get("state") if isinstance(data.get("state"), dict) else None,
    )


_FORWARD_ENV_KEYS = (
    "MYRM_STACK_ATTACH_WAIT_SEC",
    "MYRM_STACK_FRONTEND_WAIT_SEC",
    "MYRM_CLIENT_WARMUP_TIMEOUT_SEC",
    "MYRM_CHROME_E2E_PORT",
    "MYRM_CHROME_E2E_ATTACH",
    "MYRM_BACKEND_PORT",
    "MYRM_FRONTEND_PORT",
    "MYRM_FRONTEND_DEV_SCRIPT",
    "MYRM_DATA_DIR",
    "MYRM_DEV_SCRIPTS_DIR",
    "MYRM_BACKEND_PID_FILE",
    "MYRM_BACKEND_LOG_FILE",
    "E2E_UI_BASE",
    "E2E_API_BASE",
    "API_PORT",
    "PORT",
)


def _forward_env() -> dict[str, str]:
    return {key: os.environ[key] for key in _FORWARD_ENV_KEYS if key in os.environ}


def call_rpc(paths: StackPaths, command: RpcCommand, timeout_sec: float = 600.0) -> RpcResponse:
    payload = json.dumps({"cmd": command, "env": _forward_env()}) + "\n"
    with _connect(paths) as sock:
        sock.sendall(payload.encode("utf-8"))
        return _read_response(sock, timeout_sec=timeout_sec)


def _supervisor_script(paths: StackPaths) -> Path:
    return paths.dev_stack_sh.parent / "stack-supervisor.sh"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def supervisor_running(paths: StackPaths) -> bool:
    if not paths.supervisor_pid_file.is_file():
        return False
    raw = paths.supervisor_pid_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return False
    pid = int(raw)
    if not _pid_alive(pid):
        return False
    if not paths.supervisor_sock.exists():
        return False
    try:
        response = call_rpc(paths, "ping", timeout_sec=2.0)
    except (OSError, json.JSONDecodeError, socket.timeout):
        return False
    return response.ok


def ensure_supervisor(paths: StackPaths) -> None:
    if supervisor_running(paths):
        return
    script = _supervisor_script(paths)
    if not script.is_file():
        raise RuntimeError(f"Missing supervisor launcher: {script}")
    result = subprocess.run(
        ["bash", str(script), "start"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to start stack supervisor: {result.stderr or result.stdout}"
        )
    for _ in range(30):
        if supervisor_running(paths):
            return
        time.sleep(0.2)
    raise RuntimeError("Stack supervisor did not become ready within 6s")


def delegate_dev_stack(command: RpcCommand) -> int:
    paths = resolve_paths()
    ensure_supervisor(paths)
    response = call_rpc(paths, command)
    if response.stdout:
        sys.stdout.write(response.stdout)
        if not response.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if response.stderr:
        sys.stderr.write(response.stderr)
        if not response.stderr.endswith("\n"):
            sys.stderr.write("\n")
    return response.exit_code


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: client.py <ensure|attach|reset|status|ping>", file=sys.stderr)
        return 1
    command = sys.argv[1]
    if command not in ("ensure", "attach", "reset", "status", "ping", "shutdown"):
        print(f"Unknown command: {command}", file=sys.stderr)
        return 1
    return delegate_dev_stack(command)  # type: ignore[arg-type]


if __name__ == "__main__":
    raise SystemExit(main())
