"""Read dev stack epoch written by scripts/dev (parallel Agent drift detection).

[INPUT]
- `~/.local/state/myrm-dev/stack-epoch.json` (override: `MYRM_STACK_EPOCH_FILE`)

[OUTPUT]
- `StackEpochPayload` / `read_stack_epoch()` for `/api/v1/health`（含 `source_fingerprint`）

[POS]
Dev-only backend generation SSOT; shell bumps on restart, API exposes for Agent drift checks.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TypedDict


class StackEpochPayload(TypedDict):
    epoch: int
    backend_pid: int | None
    started_at: str
    harness_fingerprint: str
    source_fingerprint: str


def _stack_epoch_file() -> Path:
    override = os.getenv("MYRM_STACK_EPOCH_FILE", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".local/state/myrm-dev/stack-epoch.json"


def read_stack_epoch() -> StackEpochPayload | None:
    """Load stack epoch snapshot if the dev supervisor wrote one."""
    path = _stack_epoch_file()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None

    epoch = raw.get("epoch")
    if not isinstance(epoch, int) or epoch < 1:
        return None

    backend_pid = raw.get("backend_pid")
    if backend_pid is not None and not isinstance(backend_pid, int):
        backend_pid = None

    started_at = raw.get("started_at")
    if not isinstance(started_at, str):
        started_at = ""

    harness_fingerprint = raw.get("harness_fingerprint")
    if not isinstance(harness_fingerprint, str):
        harness_fingerprint = ""

    source_fingerprint = raw.get("source_fingerprint")
    if not isinstance(source_fingerprint, str):
        source_fingerprint = ""

    return {
        "epoch": epoch,
        "backend_pid": backend_pid,
        "started_at": started_at,
        "harness_fingerprint": harness_fingerprint,
        "source_fingerprint": source_fingerprint,
    }


__all__ = ["StackEpochPayload", "read_stack_epoch"]
