"""Delete legacy on-disk canvas snapshot directory if present.

[INPUT]
(none — leaf utility)

[OUTPUT]
- remove_retired_canvas_data_dir: delete ~/.myrm/canvas if present

[POS]
Filesystem companion to ``DROP TABLE IF EXISTS canvas`` in migrations.py.
Legacy installs may still have tldraw JSON under ``~/.myrm/canvas/{uuid}/``.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

RETIRED_CANVAS_DATA_DIR = Path.home() / ".myrm" / "canvas"


def remove_retired_canvas_data_dir() -> None:
    """Delete legacy tldraw snapshot directory under ``~/.myrm/canvas/`` when present."""
    target = RETIRED_CANVAS_DATA_DIR
    if not target.exists():
        return
    try:
        shutil.rmtree(target)
        logger.info("Removed retired canvas data directory: %s", target)
    except OSError as exc:
        logger.warning("Failed to remove retired canvas data directory: %s", exc)
