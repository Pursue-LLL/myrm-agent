"""Touch monotonic wall progress for Chrome E2E (R39)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

ENV_PROGRESS_AT = "MYRM_E2E_WALL_PROGRESS_AT_MONOTONIC"
_PROGRESS_BASENAME = "myrm-e2e-wall-progress.json"


def wall_progress_path() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / _PROGRESS_BASENAME


def touch_e2e_wall_progress() -> None:
    stamp = time.monotonic()
    os.environ[ENV_PROGRESS_AT] = str(stamp)
    path = wall_progress_path()
    path.write_text(json.dumps({"atMonotonic": stamp}), encoding="utf-8")


def read_wall_progress_monotonic() -> float | None:
    env_raw = os.environ.get(ENV_PROGRESS_AT, "").strip()
    if env_raw:
        try:
            return float(env_raw)
        except ValueError:
            pass
    path = wall_progress_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = payload.get("atMonotonic")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
