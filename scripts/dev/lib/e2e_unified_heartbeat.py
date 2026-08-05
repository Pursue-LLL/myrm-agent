"""Unified E2E session heartbeat SSOT (P0-D): coordinator + wave lease + runtime."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _wave_script() -> Path:
    return Path(__file__).resolve().parents[1] / "wave.sh"


def shell_heartbeat_loop_active() -> bool:
    """True when test.sh bootstrap owns the background heartbeat subprocess."""
    pid_raw = os.environ.get("MYRM_E2E_SESSION_HEARTBEAT_PID", "").strip()
    if not pid_raw.isdigit():
        return False
    pid = int(pid_raw)
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def pytest_should_spawn_heartbeat_loop() -> bool:
    """Pytest must not duplicate the shell-owned 30s heartbeat loop."""
    if os.environ.get("MYRM_E2E_PYTEST_HEARTBEAT_LOOP", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    return not shell_heartbeat_loop_active()


def _heartbeat_wave_lease(*, extend_sec: int = 900) -> None:
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    agent_id = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if not lease_id or not agent_id:
        return
    try:
        result = subprocess.run(
            [
                "bash",
                str(_wave_script()),
                "--agent",
                agent_id,
                "lease",
                "heartbeat",
                lease_id,
                "--extend",
                str(extend_sec),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return
    if result.returncode != 0:
        message = result.stderr or result.stdout
        if "LEASE_NOT_ACTIVE" in message or "LEASE_NOT_FOUND" in message:
            return
        if "TimeoutError" in message or "timed out" in message:
            return
        raise RuntimeError(f"E2E_LEASE_HEARTBEAT_FAIL: {message}")


def _heartbeat_dev_gate_session(*, current_node: str | None = None) -> None:
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
    if not run_id or not token:
        return
    node = current_node or os.environ.get("E2E_ADMIT_NODE", "E2E_BODY")
    try:
        from dev_gate_cli import default_socket_path, normalized_socket_path  # noqa: PLC0415
        from dev_gate_coordinator import request  # noqa: PLC0415

        socket_path = normalized_socket_path(default_socket_path())
        request(
            {
                "operation": "heartbeat",
                "session_id": run_id,
                "owner_token": token,
                "current_node": node,
            },
            socket_path=socket_path,
            timeout_sec=3.0,
        )
    except (ConnectionError, OSError, RuntimeError, TimeoutError, ValueError):
        return


def _heartbeat_private_runtime_once() -> None:
    runtime_id = os.environ.get("MYRM_E2E_PRIVATE_RUNTIME_ID", "").strip()
    if not runtime_id:
        runtime_id = os.environ.get("MYRM_E2E_RUNTIME_ID", "").strip()
    token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
    if not runtime_id or not token:
        return
    dev_dir = Path(__file__).resolve().parents[1]
    script = dev_dir / "isolated_runtime.py"
    if not script.is_file():
        return
    try:
        subprocess.run(
            [
                sys.executable,
                str(script),
                "heartbeat",
                runtime_id,
                "--owner-token",
                token,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return


def _touch_dedupe_holder_progress(*, current_node: str | None = None) -> None:
    holder_raw = os.environ.get("MYRM_E2E_DEDUPE_HOLDER_PID", "").strip()
    if not holder_raw.isdigit():
        return
    from e2e_session_snapshot import touch_holder_session_progress

    touch_holder_session_progress(
        holder_pid=int(holder_raw),
        current_node=current_node or os.environ.get("E2E_ADMIT_NODE"),
    )


def heartbeat_once(*, current_node: str | None = None) -> None:
    """Single coordinator/wave/runtime heartbeat tick for shell and pytest."""
    _heartbeat_wave_lease()
    _touch_dedupe_holder_progress(current_node=current_node)
    _heartbeat_private_runtime_once()
    _heartbeat_dev_gate_session(current_node=current_node)
