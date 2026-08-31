"""Resolved paths for the Chrome E2E marathon supervisor."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarathonPaths:
    monorepo_root: Path
    agent_root: Path
    state_dir: Path
    test_sh: Path
    ledger_file: Path
    lock_file: Path
    log_dir: Path
    pid_file: Path
    sock_file: Path
    daemon_log: Path


def resolve_paths() -> MarathonPaths:
    dev_lib = Path(__file__).resolve().parent.parent
    dev_dir = dev_lib.parent
    if str(dev_dir) not in sys.path:
        sys.path.insert(0, str(dev_dir))
    agent_root = dev_dir.parent.parent
    monorepo_root = agent_root.parent
    state_override = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if state_override:
        state_dir = Path(state_override).resolve()
    else:
        from wave_orchestrator.paths import resolve_dev_state_dir

        state_dir = resolve_dev_state_dir()
    sock_override = os.environ.get("MYRM_MARATHON_SOCKET", "").strip()
    sock_file = Path(sock_override) if sock_override else state_dir / "marathon.sock"
    return MarathonPaths(
        monorepo_root=monorepo_root,
        agent_root=agent_root,
        state_dir=state_dir,
        test_sh=monorepo_root / "scripts" / "dev" / "test.sh",
        ledger_file=state_dir / "marathon-ledger.json",
        lock_file=state_dir / "marathon-lock.json",
        log_dir=state_dir / "marathon-logs",
        pid_file=state_dir / "marathon.pid",
        sock_file=sock_file,
        daemon_log=state_dir / "marathon-supervisor.log",
    )
