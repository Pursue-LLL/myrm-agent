"""SQLite WAL registry and event journal for Dev Gate Chrome E2E sessions."""

from __future__ import annotations

import os
from pathlib import Path

from e2e_core.real_user_home import real_user_home

from dev_gate.store.ownership import OwnershipConflictError, OwnershipMixin
from dev_gate.store.progress import ProgressMixin
from dev_gate.store.queries import QueryMixin
from dev_gate.store.reaper import ReaperMixin
from dev_gate.store.terminal import TerminalMixin

__all__ = ["DevGateStore", "OwnershipConflictError", "default_store_path"]


def default_store_path() -> Path:
    override = os.environ.get("MYRM_DEV_GATE_DB", "").strip()
    if override:
        return Path(override).resolve()
    return real_user_home() / ".local/state/myrm-dev-gate/coordinator.sqlite3"


class DevGateStore(ProgressMixin, TerminalMixin, OwnershipMixin, ReaperMixin, QueryMixin):
    """SQLite registry of Dev Gate sessions, their ownership rows and the event journal."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_store_path()).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
