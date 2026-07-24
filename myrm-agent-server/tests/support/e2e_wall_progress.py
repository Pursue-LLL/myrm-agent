"""Touch monotonic wall progress for Chrome E2E (R39)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

ENV_PROGRESS_AT = "MYRM_E2E_WALL_PROGRESS_AT_MONOTONIC"
_PROGRESS_BASENAME = "myrm-e2e-wall-progress.json"


def wall_progress_path() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / _PROGRESS_BASENAME


def touch_e2e_wall_progress() -> None:
    stamp = time.monotonic()
    os.environ[ENV_PROGRESS_AT] = str(stamp)
    path = wall_progress_path()
    path.write_text(json.dumps({"atMonotonic": stamp}), encoding="utf-8")


def reset_e2e_wall_budget_clock() -> None:
    """Reset monotonic wall budget at each desktop approval retry attempt."""
    stamp = time.monotonic()
    os.environ["MYRM_E2E_WALL_STARTED_MONOTONIC"] = str(stamp)
    os.environ[ENV_PROGRESS_AT] = str(stamp)
    wall_progress_path().write_text(
        json.dumps({"atMonotonic": stamp}),
        encoding="utf-8",
    )


def reset_chrome_e2e_body_clocks(*, timeout_sec: int, item: pytest.Item) -> None:
    """R48: SHPOIB/bootstrap complete — start fresh 600s body + pytest-timeout budgets."""
    reset_e2e_wall_budget_clock()
    try:
        import pytest_timeout

        pytest_timeout.pytest_timeout_cancel_timer(item)
        base = pytest_timeout._get_item_settings(item)
        settings = pytest_timeout.Settings(
            int(timeout_sec),
            base.method,
            base.func_only,
            base.disable_debugger_detection,
        )
        pytest_timeout.pytest_timeout_set_timer(item, settings)
    except ImportError:
        pass
    print(
        f"E2E_BODY_CLOCK_RESET: timeout={int(timeout_sec)}s "
        "(SHPOIB/bootstrap excluded from body budget)",
        flush=True,
    )


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
