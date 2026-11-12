"""Where runtime epoch state lives and how it is read.

[INPUT]
- MYRM_DEV_STATE_DIR / MYRM_STACK_EPOCH_FILE overrides, else `wave_orchestrator.paths.resolve_dev_state_dir()` (POS: dev state dir SSOT)

[OUTPUT]
- `state_dir()`: dev state directory (holds `stack-epoch.json` and `frontend-warmth.json`)
- `stack_epoch_file()`: path of `stack-epoch.json`
- `read_json_file()`: parsed JSON object, or `None` when the file is missing or malformed

[POS]
Leaf helper of the epoch readers (`runtime_identity`, `frontend_epoch`); knows no epoch's shape.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def state_dir() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override)
    from dev_paths import scripts_dev_dir

    dev_dir = scripts_dev_dir(Path(__file__))
    dev_dir_str = str(dev_dir)
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_dev_state_dir

    return resolve_dev_state_dir()


def stack_epoch_file() -> Path:
    override = os.getenv("MYRM_STACK_EPOCH_FILE", "").strip()
    if override:
        return Path(override)
    return state_dir() / "stack-epoch.json"


def read_json_file(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    return raw
