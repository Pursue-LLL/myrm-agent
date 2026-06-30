"""Canvas agent-facing operations.

[INPUT]
- app.services.canvas._paths (POS: Shared canvas filesystem path utilities)

[OUTPUT]
- get_canvas_state: Retrieve the full tldraw snapshot for a canvas
- get_canvas_selection: Retrieve current user selection on a canvas
- insert_canvas_element: Insert a tldraw shape into a canvas

[POS]
Service-layer operations enabling Agent ↔ canvas interaction. These functions
are the backend for MCP tools and internal agent tools that need to read or
write canvas state programmatically. SSE notification is the caller's
responsibility (api layer), not this module's.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from app.services.canvas._paths import canvas_dir, selection_path, snapshot_path

logger = logging.getLogger(__name__)


async def get_canvas_state(canvas_id: str) -> dict[str, Any] | None:
    """Retrieve the full tldraw snapshot JSON for a canvas.

    Returns None if no snapshot exists yet.
    """
    path = snapshot_path(canvas_id)
    if not path.exists():
        return None
    try:
        content = await asyncio.to_thread(path.read_text, "utf-8")
        return json.loads(content)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read canvas snapshot %s: %s", canvas_id, e)
        return None


async def get_canvas_selection(canvas_id: str) -> list[dict[str, Any]]:
    """Retrieve the current user-selected shapes on a canvas.

    Returns an empty list if nothing is selected.
    """
    path = selection_path(canvas_id)
    if not path.exists():
        return []
    try:
        content = await asyncio.to_thread(path.read_text, "utf-8")
        data = json.loads(content)
        return data.get("selectedShapes", [])
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read canvas selection %s: %s", canvas_id, e)
        return []


async def insert_canvas_element(
    canvas_id: str,
    shape_type: str,
    x: float,
    y: float,
    props: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert a new tldraw shape into a canvas snapshot.

    Reads the current snapshot, adds the shape, and writes back.
    The caller is responsible for triggering SSE notification if needed.

    Returns the created shape record.
    """
    snap_path = snapshot_path(canvas_id)
    cdir = canvas_dir(canvas_id)
    cdir.mkdir(parents=True, exist_ok=True)

    if snap_path.exists():
        try:
            raw = await asyncio.to_thread(snap_path.read_text, "utf-8")
            snapshot: dict[str, Any] = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            snapshot = {"store": {}}
    else:
        snapshot = {"store": {}}

    store = snapshot.get("store", {})
    if isinstance(store, list):
        store = {
            item.get("id", str(i)): item
            for i, item in enumerate(store)
            if isinstance(item, dict)
        }
        snapshot["store"] = store

    shape_id = f"shape:{uuid.uuid4().hex[:16]}"
    shape_props = props or {}
    if shape_type in ("text", "note") and "text" not in shape_props:
        shape_props["text"] = ""

    shape: dict[str, Any] = {
        "id": shape_id,
        "type": shape_type,
        "x": x,
        "y": y,
        "rotation": 0,
        "isLocked": False,
        "props": shape_props,
        "typeName": "shape",
    }

    store[shape_id] = shape
    snapshot["store"] = store

    await asyncio.to_thread(
        snap_path.write_text,
        json.dumps(snapshot, ensure_ascii=False),
        "utf-8",
    )

    return shape
