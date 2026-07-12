"""Resolved paths for the dev stack supervisor."""

from __future__ import annotations

import os
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
    state_dir = Path(
        os.environ.get("MYRM_DEV_STATE_DIR", Path.home() / ".local/state/myrm-dev")
    ).resolve()
    return StackPaths(
        agent_root=root,
        server_dir=root / "myrm-agent-server",
        frontend_dir=root / "myrm-agent-frontend",
        dev_stack_sh=root / "scripts/dev/dev-stack.sh",
        state_dir=state_dir,
        supervisor_pid_file=state_dir / "supervisor.pid",
        supervisor_sock=state_dir / "supervisor.sock",
        supervisor_state_file=state_dir / "supervisor-state.json",
        backend_pid_file=root / "myrm-agent-server/.myrm-dev-backend.pid",
        frontend_pid_file=root / "myrm-agent-frontend/.myrm-dev-frontend.pid",
        frontend_lock_file=root / "myrm-agent-frontend/.next/dev-server.lock",
        warmth_file=state_dir / "frontend-warmth.json",
        epoch_file=state_dir / "stack-epoch.json",
        api_health_url="http://127.0.0.1:8080/api/v1/health",
        app_url="http://127.0.0.1:3000/",
        frontend_port=3000,
    )
