"""Live stack probe and RUNTIME_DRIFT checks for Chrome MCP E2E.

[INPUT]
- runtime_identity.py epoch readers (POS: Runtime Identity SSOT)

[OUTPUT]
- probe_runtime_context() / read_current_runtime_id() / _read_shared_hot_stack_runtime_id() / run_drift_check()
- _read_shared_hot_stack_runtime_id() is the shared hot-stack runtimeId SSOT (used by e2e_runtime_guard heal paths)

[POS]
Dev infrastructure. Observes mux/CDP/frontend without mutating the stack.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from runtime_identity import (
    RuntimeProbeContext,
    _default_chrome_data_dir,
    _mux_state_dir,
    _resolve_e2e_port,
    collect_runtime_parts,
    compute_hot_pool_runtime_id,
    read_chrome_epoch,
    runtime_ids_equal,
)


def _default_frontend_dir() -> Path | None:
    override = os.getenv("MYRM_FRONTEND_DIR", "").strip()
    if override:
        return Path(override)
    lib_dir = Path(__file__).resolve().parent
    candidate = lib_dir.parent.parent.parent / "myrm-agent-frontend"
    if candidate.is_dir():
        return candidate
    return None


def _resolve_mux_bin() -> Path | None:
    override = os.getenv("CDMCP_MUX_BIN", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    lib_dir = Path(__file__).resolve().parent
    agent_root = lib_dir.parent.parent.parent
    monorepo_override = os.getenv("MYRM_MONOREPO_ROOT", "").strip()
    monorepo_root = Path(monorepo_override) if monorepo_override else agent_root.parent
    candidate = (
        monorepo_root
        / "scripts"
        / "dev"
        / "cdmcp-mux-autoconnect"
        / "bin"
        / "cdmcp-mux-autoconnect.mjs"
    )
    return candidate if candidate.is_file() else None


def _count_mux_daemons_from_ps(output: str) -> int:
    count = 0
    for line in output.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) != 2:
            continue
        try:
            argv = shlex.split(fields[1])
        except ValueError:
            continue
        if (
            len(argv) >= 3
            and Path(argv[-3]).name == "node"
            and Path(argv[-2]).name == "cdmcp-mux-autoconnect.mjs"
            and argv[-1] == "daemon"
        ):
            count += 1
    return count


def _mux_daemon_count() -> int:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0
    if proc.returncode != 0:
        return 0
    return _count_mux_daemons_from_ps(proc.stdout)


def _mux_status_snapshot() -> tuple[bool, int]:
    if _mux_daemon_count() < 1:
        return False, 0
    mux_bin = _resolve_mux_bin()
    if mux_bin is None:
        return False, 0
    try:
        proc = subprocess.run(
            ["node", str(mux_bin), "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, 0
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, 0
    if not isinstance(payload, dict):
        return False, 0
    generation = payload.get("upstreamGeneration")
    return bool(payload.get("upstreamReady")), generation if isinstance(generation, int) else 0


def _mux_upstream_ready() -> bool:
    return _mux_status_snapshot()[0]


def _mux_ws_stamp_matches(cdp_port: int) -> bool:
    stamp_path = _mux_state_dir() / "upstream-ws-url"
    if not stamp_path.is_file():
        return False
    stored = stamp_path.read_text(encoding="utf-8").strip()
    if not stored:
        return False
    chrome = read_chrome_epoch(cdp_port)
    if chrome is None:
        return False
    return stored == chrome["web_socket_url"]


def probe_runtime_context() -> RuntimeProbeContext:
    port = _resolve_e2e_port()
    frontend = _default_frontend_dir()
    profile = _default_chrome_data_dir()
    upstream_ready, upstream_generation = _mux_status_snapshot()
    return {
        "mux_daemon_count": _mux_daemon_count(),
        "upstream_ready": upstream_ready,
        "upstream_generation": upstream_generation,
        "ws_stamp_matches": _mux_ws_stamp_matches(port),
        "frontend_dir": str(frontend) if frontend is not None else "",
        "cdp_port": port,
        "profile_dir": str(profile),
    }


def _read_shared_hot_stack_runtime_id() -> str:
    """Stable shared hot-pool identity for SHPOIB and the supervisor reaper."""
    shared_state = Path.home() / ".local/state/myrm-dev"
    overrides = {
        "MYRM_DEV_STATE_DIR": str(shared_state),
        "MYRM_STACK_EPOCH_FILE": str(shared_state / "stack-epoch.json"),
        "MYRM_BACKEND_PORT": "8080",
        "PORT": "8080",
        "API_PORT": "8080",
        "E2E_API_BASE": "http://127.0.0.1:8080",
        "MYRM_FRONTEND_PORT": "3000",
        "E2E_UI_BASE": "http://127.0.0.1:3000",
    }
    saved = {
        key: os.environ.get(key)
        for key in (
            *overrides,
            "MYRM_PRIVATE_BACKEND",
            "MYRM_E2E_PRIVATE_BACKEND",
            "MYRM_E2E_ISOLATED",
        )
    }
    try:
        os.environ.update(overrides)
        os.environ.pop("MYRM_PRIVATE_BACKEND", None)
        os.environ.pop("MYRM_E2E_PRIVATE_BACKEND", None)
        os.environ.pop("MYRM_E2E_ISOLATED", None)
        ctx = probe_runtime_context()
        parts = collect_runtime_parts(
            frontend_dir=Path(ctx["frontend_dir"]) if ctx["frontend_dir"] else None,
            cdp_port=ctx["cdp_port"],
            profile_dir=Path(ctx["profile_dir"]),
            upstream_ready=ctx["upstream_ready"],
            upstream_generation=ctx["upstream_generation"],
            ws_stamp_matches=ctx["ws_stamp_matches"],
            mux_daemon_count=ctx["mux_daemon_count"],
        )
        return compute_hot_pool_runtime_id(parts)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def read_current_runtime_id() -> str:
    if os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1":
        from runtime_identity import read_stack_scoped_runtime_id

        return read_stack_scoped_runtime_id()
    if (
        os.environ.get("MYRM_PRIVATE_BACKEND", "").strip() == "1"
        or os.environ.get("MYRM_E2E_PRIVATE_BACKEND", "").strip() == "1"
    ):
        return _read_shared_hot_stack_runtime_id()
    ctx = probe_runtime_context()
    parts = collect_runtime_parts(
        frontend_dir=Path(ctx["frontend_dir"]) if ctx["frontend_dir"] else None,
        cdp_port=ctx["cdp_port"],
        profile_dir=Path(ctx["profile_dir"]),
        upstream_ready=ctx["upstream_ready"],
        upstream_generation=ctx["upstream_generation"],
        ws_stamp_matches=ctx["ws_stamp_matches"],
        mux_daemon_count=ctx["mux_daemon_count"],
    )
    return compute_hot_pool_runtime_id(parts)


def run_drift_check(expected: str) -> int:
    expected_id = expected.strip()
    if not expected_id:
        print("RUNTIME_DRIFT_FAIL: --expect requires non-empty runtimeId", file=sys.stderr)
        return 1
    current = read_current_runtime_id()
    if runtime_ids_equal(current, expected_id):
        print(f"RUNTIME_DRIFT_OK: runtimeId={current}")
        return 0
    print(
        f"RUNTIME_DRIFT: expected={expected_id} current={current}",
        file=sys.stderr,
    )
    print("RUNTIME_DRIFT_HINT: ./myrm ready --chrome", file=sys.stderr)
    return 2
