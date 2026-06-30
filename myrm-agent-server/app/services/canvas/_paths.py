"""Canvas filesystem path helpers.

[INPUT]
(none — leaf utility)

[OUTPUT]
- CANVAS_DATA_DIR, MAX_SNAPSHOT_SIZE_BYTES: constants
- validate_canvas_id, canvas_dir, snapshot_path, selection_path: path helpers

[POS]
Shared filesystem path utilities for canvas data storage. Used by both
the REST API router and the service-layer operations to avoid DRY violations.
Lives in services/ so that api/ imports from services/ (correct dependency
direction: api → services).
"""

from __future__ import annotations

import re
from pathlib import Path

CANVAS_DATA_DIR = Path.home() / ".myrm" / "canvas"
MAX_SNAPSHOT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def validate_canvas_id(canvas_id: str) -> None:
    """Raise ValueError if canvas_id is not a valid UUID (path traversal guard)."""
    if not _UUID_PATTERN.match(canvas_id):
        raise ValueError(f"Invalid canvas ID format: {canvas_id}")


def canvas_dir(canvas_id: str) -> Path:
    validate_canvas_id(canvas_id)
    return CANVAS_DATA_DIR / canvas_id


def snapshot_path(canvas_id: str) -> Path:
    return canvas_dir(canvas_id) / "snapshot.json"


def selection_path(canvas_id: str) -> Path:
    return canvas_dir(canvas_id) / "selection.json"
