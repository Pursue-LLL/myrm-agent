"""Resolved paths for the dev stack supervisor."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StackPaths:
    agent_root: Path
    server_dir: Path
    frontend_dir: Path
    dev_stack_sh: Path
    state_dir: Path
    supervisor_pid_file: Path
    supervisor_sock: Path
    supervisor_state_file: Path
    backend_pid_file: Path
    frontend_pid_file: Path
    frontend_lock_file: Path
    warmth_file: Path
    epoch_file: Path
    api_health_url: str
    app_url: str
    frontend_port: int


def _resolve_agent_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    env_root = os.environ.get("AGENT_ROOT", "").strip()
    if env_root:
        return Path(env_root).resolve()
    dev_dir = Path(__file__).resolve().parent.parent
    candidate = dev_dir.parent
    if (candidate / "myrm-agent-server" / "run.py").is_file():
        return candidate.resolve()
    raise RuntimeError("Cannot resolve AGENT_ROOT — set AGENT_ROOT or run via stack-supervisor.sh")


def resolve_paths(agent_root: str | None = None) -> StackPaths:
    root = _resolve_agent_root(agent_root)
    dev_dir = Path(__file__).resolve().parent.parent
    dev_dir_str = str(dev_dir)
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_dev_state_dir

    state_dir = resolve_dev_state_dir()
    socket_override = os.environ.get("MYRM_SUPERVISOR_SOCKET", "").strip()
    supervisor_sock = Path(socket_override) if socket_override else state_dir / "supervisor.sock"
    backend_port = int(os.environ.get("MYRM_BACKEND_PORT", os.environ.get("PORT", "8080")))
    frontend_port = int(os.environ.get("MYRM_FRONTEND_PORT", "3000"))
    api_base = os.environ.get("E2E_API_BASE", f"http://127.0.0.1:{backend_port}").rstrip("/")
    app_url = os.environ.get("E2E_UI_BASE", f"http://127.0.0.1:{frontend_port}").rstrip("/")
    dev_scripts_override = os.environ.get("MYRM_DEV_SCRIPTS_DIR", "").strip()
    dev_scripts = Path(dev_scripts_override) if dev_scripts_override else root / "scripts/dev"
    return StackPaths(
        agent_root=root,
        server_dir=root / "myrm-agent-server",
        frontend_dir=root / "myrm-agent-frontend",
        dev_stack_sh=dev_scripts / "dev-stack.sh",
        state_dir=state_dir,
        supervisor_pid_file=state_dir / "supervisor.pid",
        supervisor_sock=supervisor_sock,
        supervisor_state_file=state_dir / "supervisor-state.json",
        backend_pid_file=state_dir / "backend.pid",
        frontend_pid_file=state_dir / "frontend.pid",
        frontend_lock_file=root / "myrm-agent-frontend/.next/dev-server.lock",
        warmth_file=state_dir / "frontend-warmth.json",
        epoch_file=state_dir / "stack-epoch.json",
        api_health_url=f"{api_base}/api/v1/health",
        app_url=f"{app_url}/",
        frontend_port=frontend_port,
    )
