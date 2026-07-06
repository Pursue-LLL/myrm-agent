"""One-time cleanup for the removed Infinite Canvas product module.

[INPUT]
(none — leaf utility)

[OUTPUT]
- remove_retired_canvas_data_dir: delete ~/.myrm/canvas if present

[POS]
Filesystem companion to ``DROP TABLE IF EXISTS canvas`` in migrations.py.
The deleted Canvas module stored tldraw JSON under ``~/.myrm/canvas/{uuid}/``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

RETIRED_CANVAS_DATA_DIR = Path.home() / ".myrm" / "canvas"


def remove_retired_canvas_data_dir() -> None:
    """Delete legacy tldraw snapshot directory from the removed Canvas module."""
    target = RETIRED_CANVAS_DATA_DIR
    if not target.exists():
        return
    try:
        shutil.rmtree(target)
        logger.info("Removed retired canvas data directory: %s", target)
    except OSError as exc:
        logger.warning("Failed to remove retired canvas data directory: %s", exc)
