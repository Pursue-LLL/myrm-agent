"""Unified E2E session heartbeat SSOT (P0-D): coordinator + wave lease + runtime.

[INPUT]
- e2e_session_runtime.snapshot per-pid sidecars (POS: parallel-safe progress for ./myrm e2e-context and hung pytest reap)
- dev_gate_cli / dev_gate_coordinator (POS: Unix socket 协调器与自动启动客户端；受限环境回退同一 SQLite 事务路径)
- scripts/dev/lib/e2e_bootstrap.sh · scripts/dev/test.sh — shell 30s 心跳循环调用方

[OUTPUT]
- heartbeat_once: coordinator + wave lease + runtime 统一心跳
- _snapshot_current_node: 从 pytest session snapshot 解析真实节点，桥接 shell 心跳转发 coordinator

[POS]
Dev Gate layer — 统一 E2E heartbeat SSOT（coordinator + wave lease + private runtime）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _wave_script() -> Path:
    return Path(__file__).resolve().parents[2] / "wave.sh"


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


def _pytest_uses_isolated_wave_state() -> bool:
    """True when pytest owns a private wave-orchestrator.json (SHPOIB / isolated runtime).

    The shell-owned heartbeat extends leases in the holder's shared wave file. After
    ``_chrome_e2e_item_runtime`` monkeypatches ``MYRM_WAVE_STATE_DIR`` to the
    private runtime state dir, orchestrator lease attestation and reap observe the
    isolated file — pytest must heartbeat that lease itself or contexts are reaped
    mid-body (``No context for session orch-*``).
    """
    if os.environ.get("MYRM_E2E_PRIVATE_BACKEND", "").strip() == "1":
        return True
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1":
        return True
    wave_raw = os.environ.get("MYRM_WAVE_STATE_DIR", "").strip()
    if not wave_raw:
        return False
    try:
        wave_dir = Path(wave_raw).resolve()
    except OSError:
        return False
    from e2e_core.real_user_home import real_user_home

    shared = (real_user_home() / ".local/state/myrm-dev").resolve()
    return wave_dir != shared


def pytest_should_spawn_heartbeat_loop() -> bool:
    """Pytest must not duplicate the shell-owned 30s heartbeat loop."""
    if os.environ.get("MYRM_E2E_PYTEST_HEARTBEAT_LOOP", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        return False
    if _pytest_uses_isolated_wave_state():
        return True
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


def _snapshot_current_node() -> str:
    """Resolve pytest's latest per-step node from the live session snapshot.

    The shell-owned 30s heartbeat never sees pytest's per-step node (pytest only
    persists it via ``touch_wall_progress``), so without this bridge the
    coordinator registry stays stuck on an admit node while pytest advances.
    """
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    if not run_id:
        return ""
    try:
        from e2e_session_runtime.snapshot import _load_all_session_snapshots
    except ImportError:
        return ""
    matched = [
        str(payload.get("currentNode") or "").strip()
        for _pid, payload in _load_all_session_snapshots(live_only=True)
        if str(payload.get("runId") or "").strip() == run_id
    ]
    matched = [node for node in matched if node]
    if not matched:
        return ""
    real = [node for node in matched if not node.startswith("E2E_")]
    return real[0] if real else matched[0]


def _heartbeat_dev_gate_session(*, current_node: str | None = None) -> None:
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
    if not run_id or not token:
        return
    resolved_node = (current_node or "").strip()
    if not resolved_node:
        resolved_node = _snapshot_current_node()
    try:
        from dev_gate.cli import (
            default_socket_path,
            normalized_socket_path,
        )
        from dev_gate.coordinator import request

        socket_path = normalized_socket_path(default_socket_path())
        payload = {
            "operation": "heartbeat",
            "session_id": run_id,
            "owner_token": token,
        }
        if resolved_node:
            payload["current_node"] = resolved_node
        request(
            payload,
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
    # isolated_runtime stays a root-level domain package; resolve it from the
    # monorepo root rather than this package dir (scripts/dev/lib/e2e_session_runtime).
    script = (
        Path(__file__).resolve().parents[5]
        / "scripts"
        / "dev"
        / "isolated_runtime"
        / "cli.py"
    )
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
    from e2e_session_runtime.snapshot import touch_holder_session_progress

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
