"""Canvas agent-facing operations.

[INPUT]
- app.services.canvas._paths (POS: Shared canvas filesystem path utilities)

[OUTPUT]
- get_canvas_state: Retrieve the full tldraw snapshot for a canvas
- get_canvas_selection: Retrieve current user selection on a canvas
- insert_canvas_element: Insert a tldraw shape into a canvas
- batch_insert_canvas_elements: Insert multiple shapes + arrows atomically
- save_canvas_snapshot: Atomically replace a full canvas snapshot (frontend save)

[POS]
Service-layer operations enabling Agent ↔ canvas interaction. These functions
are the backend for agent tools and the REST API that need to read or write
canvas state programmatically. SSE notification is the caller's
responsibility (via _events.notify_canvas_change), not this module's.

All write operations acquire a per-canvas asyncio.Lock to prevent lost updates
when the frontend auto-save and Agent insert race on the same snapshot file.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from typing import Any

from app.services.canvas._paths import canvas_dir, selection_path, snapshot_path

logger = logging.getLogger(__name__)

_canvas_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


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
    async with _canvas_locks[canvas_id]:
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


async def batch_insert_canvas_elements(
    canvas_id: str,
    shapes: list[dict[str, Any]],
    arrows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Insert multiple shapes and arrows atomically into a canvas.

    Each shape dict: {"id": "logical_id", "type": str, "x": float, "y": float, "props": {...}}
    Each arrow dict: {"from_id": "logical_id", "to_id": "logical_id"}

    Returns {"inserted_shapes": [...], "inserted_arrows": [...]} with actual shape IDs.
    """
    async with _canvas_locks[canvas_id]:
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

        id_map: dict[str, str] = {}
        inserted_shapes: list[dict[str, Any]] = []

        for shape_def in shapes:
            logical_id = shape_def.get("id", "")
            shape_type = shape_def.get("type", "note")
            x = float(shape_def.get("x", 0))
            y = float(shape_def.get("y", 0))
            props = shape_def.get("props", {})

            shape_id = f"shape:{uuid.uuid4().hex[:16]}"
            id_map[logical_id] = shape_id

            if shape_type in ("text", "note") and "text" not in props:
                props["text"] = ""

            shape: dict[str, Any] = {
                "id": shape_id,
                "type": shape_type,
                "x": x,
                "y": y,
                "rotation": 0,
                "isLocked": False,
                "props": props,
                "typeName": "shape",
            }
            store[shape_id] = shape
            inserted_shapes.append(shape)

        inserted_arrows: list[dict[str, Any]] = []
        shape_centers: dict[str, tuple[float, float]] = {}
        for shape_def in shapes:
            lid = shape_def.get("id", "")
            cx = float(shape_def.get("x", 0)) + 140
            cy = float(shape_def.get("y", 0)) + 60
            shape_centers[lid] = (cx, cy)

        for arrow_def in arrows or []:
            from_logical = arrow_def.get("from_id", "")
            to_logical = arrow_def.get("to_id", "")
            if from_logical not in id_map or to_logical not in id_map:
                continue
            from_center = shape_centers.get(from_logical, (0, 0))
            to_center = shape_centers.get(to_logical, (0, 0))

            arrow_id = f"shape:{uuid.uuid4().hex[:16]}"
            arrow: dict[str, Any] = {
                "id": arrow_id,
                "type": "arrow",
                "x": from_center[0],
                "y": from_center[1],
                "rotation": 0,
                "isLocked": False,
                "props": {
                    "start": {"x": 0, "y": 0},
                    "end": {
                        "x": to_center[0] - from_center[0],
                        "y": to_center[1] - from_center[1],
                    },
                    "color": arrow_def.get("color", "black"),
                    "labelColor": "black",
                    "text": arrow_def.get("label", ""),
                },
                "typeName": "shape",
            }
            store[arrow_id] = arrow
            inserted_arrows.append(arrow)

        snapshot["store"] = store
        await asyncio.to_thread(
            snap_path.write_text,
            json.dumps(snapshot, ensure_ascii=False),
            "utf-8",
        )

        return {"inserted_shapes": inserted_shapes, "inserted_arrows": inserted_arrows}


async def save_canvas_snapshot(canvas_id: str, snapshot: dict[str, Any]) -> None:
    """Atomically replace the full canvas snapshot (frontend auto-save).

    Acquires the same per-canvas lock used by insert operations to prevent
    lost updates when the frontend PUT races with an Agent read-modify-write.
    """
    async with _canvas_locks[canvas_id]:
        cdir = canvas_dir(canvas_id)
        cdir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            snapshot_path(canvas_id).write_text,
            json.dumps(snapshot, ensure_ascii=False),
            "utf-8",
        )
