"""Verify mux daemon stamps and respond to a lightweight tools/list probe.

[INPUT]
- CDMCP mux state dir stamps and Unix socket path

[OUTPUT]
- exit 0 when daemon-start stamp matches expected ms and mux responds quickly

[POS]
Attach-mode heal gate: stamp match alone is insufficient when upstream still uses 55s.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from dev_gate_contract import LEGACY_MUX_REQUEST_TIMEOUT_MS
from real_user_home import real_user_home

MUX_UPSTREAM_TIMEOUT_EFFECTIVE_STAMP = "upstream-request-timeout-ms-effective"


def _normalize_socket_path(socket_path: str) -> str:
    if not socket_path:
        return socket_path
    return str(Path(socket_path))


def _read_stamp(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _read_daemon_pid(state_dir: Path) -> int | None:
    raw = _read_stamp(state_dir / "daemon.pid")
    if raw is None or not raw.isdigit():
        return None
    return int(raw)


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _owned_mux_socket_pids(socket_path: str) -> set[int]:
    normalized = _normalize_socket_path(socket_path)
    if not normalized or not os.path.exists(normalized):
        return set()
    try:
        proc = subprocess.run(
            ["lsof", "-t", "--", normalized],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    pids: set[int] = set()
    for line in proc.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            pid = int(text)
        except ValueError:
            continue
        if _process_alive(pid):
            pids.add(pid)
    return pids


def _mux_daemon_alive(*, state_dir: Path, socket_path: str) -> bool:
    pid = _read_daemon_pid(state_dir)
    if pid is not None and _process_alive(pid):
        return True
    return bool(_owned_mux_socket_pids(socket_path))


def _stamp_value_ms(raw: str | None) -> int | None:
    if raw is None or not raw.isdigit():
        return None
    return int(raw)


def _effective_upstream_timeout_ms(state_dir: Path) -> int | None:
    return _stamp_value_ms(
        _read_stamp(state_dir / MUX_UPSTREAM_TIMEOUT_EFFECTIVE_STAMP)
    )


def _effective_upstream_timeout_aligned(*, state_dir: Path, expected_ms: int) -> bool:
    effective_ms = _effective_upstream_timeout_ms(state_dir)
    if effective_ms is None:
        return False
    if effective_ms in LEGACY_MUX_REQUEST_TIMEOUT_MS:
        return False
    return effective_ms >= expected_ms


def _mux_tools_list_probe(socket_path: str, *, timeout_sec: float) -> bool:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )
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
                line = buffered.split(b"\n", maxsplit=1)[0].decode(
                    "utf-8", errors="replace"
                )
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


def mux_tools_list_responsive(*, timeout_sec: float = 8.0) -> bool:
    """Lightweight mux daemon responsiveness check (tools/list over Unix socket)."""
    socket_path = os.environ.get("CDMCP_MUX_SOCKET", "").strip()
    if not socket_path:
        socket_path = str(real_user_home() / ".local/state/cdmcp-mux/daemon.sock")
    if not socket_path or not os.path.exists(socket_path):
        return False
    bounded = max(0.5, min(timeout_sec, 60.0))
    return _mux_tools_list_probe(socket_path, timeout_sec=bounded)


def mux_timeout_effective(
    *,
    state_dir: Path,
    expected_ms: int,
    socket_path: str,
    probe_timeout_sec: float = 8.0,
) -> bool:
    stamp = _read_stamp(state_dir / "request-timeout-ms")
    daemon_stamp = _read_stamp(state_dir / "request-timeout-ms-at-daemon-start")
    expected = str(expected_ms)
    if stamp != expected or daemon_stamp != expected:
        return False
    stamp_ms = _stamp_value_ms(stamp)
    daemon_stamp_ms = _stamp_value_ms(daemon_stamp)
    if (
        stamp_ms in LEGACY_MUX_REQUEST_TIMEOUT_MS
        or daemon_stamp_ms in LEGACY_MUX_REQUEST_TIMEOUT_MS
    ):
        return False
    if not _mux_daemon_alive(state_dir=state_dir, socket_path=socket_path):
        return False
    if not _effective_upstream_timeout_aligned(
        state_dir=state_dir, expected_ms=expected_ms
    ):
        return False
    normalized_socket = _normalize_socket_path(socket_path)
    if not normalized_socket or not os.path.exists(normalized_socket):
        return False
    bounded_probe_sec = max(0.5, min(probe_timeout_sec, 60.0))
    return _mux_tools_list_probe(normalized_socket, timeout_sec=bounded_probe_sec)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe mux request timeout effectiveness."
    )
    parser.add_argument("--expected-ms", type=int, required=True)
    parser.add_argument("--state-dir", type=str, required=True)
    parser.add_argument(
        "--socket", type=str, default=os.environ.get("CDMCP_MUX_SOCKET", "")
    )
    parser.add_argument(
        "--probe-timeout-sec",
        type=float,
        default=8.0,
        help="tools/list probe budget (scales up under parallel Wave leases)",
    )
    args = parser.parse_args()
    ok = mux_timeout_effective(
        state_dir=Path(args.state_dir),
        expected_ms=args.expected_ms,
        socket_path=args.socket.strip(),
        probe_timeout_sec=args.probe_timeout_sec,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
