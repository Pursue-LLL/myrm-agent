"""Atomic JSON persistence for wave orchestrator state.

[INPUT]
- wave_orchestrator.types::OrchestratorState (POS: wave/lease typed records)

[OUTPUT]
- load_state() / save_state() / run_locked() — flock-protected state I/O

[POS]
Dev infrastructure persistence. Single-writer JSON store for parallel Agent leases.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import TypeVar

from wave_orchestrator.types import OrchestratorState

T = TypeVar("T")


def empty_state() -> OrchestratorState:
    return {"version": 2, "wave": None, "leases": [], "resources": []}


def load_state(path: Path) -> OrchestratorState:
    if not path.is_file():
        return empty_state()
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return empty_state()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        return empty_state()
    wave = payload.get("wave")
    leases = payload.get("leases")
    resources = payload.get("resources")
    if not isinstance(leases, list):
        leases = []
    if not isinstance(resources, list):
        resources = []
    version = int(payload.get("version", 1))
    if version < 2:
        version = 2
    return {
        "version": version,
        "wave": wave if isinstance(wave, dict) else None,
        "leases": [item for item in leases if isinstance(item, dict)],
        "resources": [item for item in resources if isinstance(item, dict)],
    }


def save_state(path: Path, state: OrchestratorState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    body = json.dumps(state, indent=2, sort_keys=True) + "\n"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


@contextmanager
def _state_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with open(lock_path, "w", encoding="utf-8") as lock_fp:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_fp.fileno(), fcntl.LOCK_UN)


def run_locked(path: Path, fn: Callable[[OrchestratorState], tuple[T, bool]]) -> T:
    with _state_lock(path):
        state = load_state(path)
        result, should_save = fn(state)
        if should_save:
            save_state(path, state)
        return result
