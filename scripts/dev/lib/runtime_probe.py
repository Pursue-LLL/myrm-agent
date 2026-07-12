"""Live stack probe and RUNTIME_DRIFT checks for Chrome MCP E2E.

[INPUT]
- runtime_identity.py epoch readers (POS: Runtime Identity SSOT)

[OUTPUT]
- probe_runtime_context() / read_current_runtime_id() / run_drift_check()

[POS]
Dev infrastructure. Observes mux/CDP/frontend without mutating the stack.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from runtime_identity import (
    RuntimeProbeContext,
    _default_chrome_data_dir,
    _mux_state_dir,
    _resolve_e2e_port,
    collect_runtime_parts,
    compute_runtime_id,
    read_chrome_epoch,
    runtime_ids_equal,
)


def _default_frontend_dir() -> Path | None:
    override = os.getenv("MYRM_FRONTEND_DIR", "").strip()
    if override:
        return Path(override)
    lib_dir = Path(__file__).resolve().parent
    candidate = lib_dir.parent.parent / "myrm-agent-frontend"
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
    candidate = (
        agent_root.parent
        / "scripts"
        / "dev"
        / "cdmcp-mux-autoconnect"
        / "bin"
        / "cdmcp-mux-autoconnect.mjs"
    )
    return candidate if candidate.is_file() else None


def _mux_daemon_count() -> int:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "cdmcp-mux-autoconnect.mjs daemon"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 0
    if proc.returncode != 0:
        return 0
    return len([line for line in proc.stdout.splitlines() if line.strip()])


def _mux_upstream_ready() -> bool:
    if _mux_daemon_count() < 1:
        return False
    mux_bin = _resolve_mux_bin()
    if mux_bin is None:
        return False
    try:
        proc = subprocess.run(
            ["node", str(mux_bin), "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("upstreamReady"))


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
    return {
        "mux_daemon_count": _mux_daemon_count(),
        "upstream_ready": _mux_upstream_ready(),
        "ws_stamp_matches": _mux_ws_stamp_matches(port),
        "frontend_dir": str(frontend) if frontend is not None else "",
        "cdp_port": port,
        "profile_dir": str(profile),
    }


def read_current_runtime_id() -> str:
    ctx = probe_runtime_context()
    parts = collect_runtime_parts(
        frontend_dir=Path(ctx["frontend_dir"]) if ctx["frontend_dir"] else None,
        cdp_port=ctx["cdp_port"],
        profile_dir=Path(ctx["profile_dir"]),
        upstream_ready=ctx["upstream_ready"],
        ws_stamp_matches=ctx["ws_stamp_matches"],
        mux_daemon_count=ctx["mux_daemon_count"],
    )
    return compute_runtime_id(parts)


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
