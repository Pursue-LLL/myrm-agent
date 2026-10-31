"""Delete legacy on-disk canvas snapshot directory if present.

[INPUT]
- myrm_agent_harness.api::resolve_data_dir (POS: Single entry point for the Myrm state root; harness and server code derive every state path from it)

[OUTPUT]
- remove_retired_canvas_data_dir: delete <state root>/canvas if present

[POS]
Filesystem companion to ``DROP TABLE IF EXISTS canvas`` in migrations.py.
Legacy installs may still have tldraw JSON under ``<state root>/canvas/{uuid}/``.
"""

from __future__ import annotations

import logging
import shutil

from myrm_agent_harness.api import resolve_data_dir

logger = logging.getLogger(__name__)


def remove_retired_canvas_data_dir() -> None:
    """Delete the legacy tldraw snapshot directory ``<state root>/canvas/`` when present."""
    target = resolve_data_dir() / "canvas"
    if not target.exists():
        return
    try:
        shutil.rmtree(target)
        logger.info("Removed retired canvas data directory: %s", target)
    except OSError as exc:
        logger.warning("Failed to remove retired canvas data directory: %s", exc)
