"""Canvas workspace REST API.

[INPUT]
- app.database.models.canvas::Canvas (POS: Infinite canvas workspace metadata)
- app.database.connection::get_db (POS: Async session provider)
- app.services.canvas._paths (POS: Shared canvas filesystem path utilities)

[OUTPUT]
- CRUD endpoints for canvas workspaces
- Snapshot save/load via filesystem
- Selection state read/write
- SSE endpoint for real-time canvas change notifications
- _notify_canvas_change: SSE trigger (consumed by service layer)

[POS]
REST API for the infinite canvas workspace. Canvas metadata is stored in
SQLite; tldraw snapshots are stored as JSON files on the filesystem under
~/.myrm/canvas/{canvas_id}/ (local / persistent volume depending on
deployment mode).
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.canvas._paths import (
    MAX_SNAPSHOT_SIZE_BYTES,
    canvas_dir,
    selection_path,
    snapshot_path,
)
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models.canvas import Canvas

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/canvas", tags=["canvas"])

_sse_events: dict[str, set[asyncio.Event]] = {}


def _notify_canvas_change(canvas_id: str) -> None:
    events = _sse_events.get(canvas_id)
    if events:
        for event in events:
            event.set()


async def _write_file(path: Path, content: str) -> None:
    await asyncio.to_thread(path.write_text, content, "utf-8")


async def _read_file(path: Path) -> str:
    return await asyncio.to_thread(path.read_text, "utf-8")


# ── Schemas ──────────────────────────────────────────────────────────


class CanvasCreateRequest(BaseModel):
    name: str = Field(default="Untitled Canvas", max_length=256)
    agent_id: str | None = Field(default=None, max_length=36)
    chat_id: str | None = Field(default=None, max_length=36)


class CanvasUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=256)
    agent_id: str | None = None
    chat_id: str | None = None
    thumbnail: str | None = None


class SnapshotSaveRequest(BaseModel):
    snapshot: dict[str, Any]
    thumbnail: str | None = None


class SelectionSaveRequest(BaseModel):
    selected_shapes: list[dict[str, Any]] = Field(default_factory=list)


def _canvas_to_dict(c: Canvas) -> dict[str, Any]:
    return {
        "id": c.id,
        "name": c.name,
        "agent_id": c.agent_id,
        "chat_id": c.chat_id,
        "thumbnail": c.thumbnail,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ── CRUD ─────────────────────────────────────────────────────────────


@router.post("")
async def create_canvas(body: CanvasCreateRequest, session: AsyncSession = Depends(get_db)):
    canvas_id = str(uuid.uuid4())
    now = datetime.utcnow()
    canvas = Canvas(
        id=canvas_id,
        name=body.name,
        agent_id=body.agent_id,
        chat_id=body.chat_id,
        created_at=now,
        updated_at=now,
    )
    session.add(canvas)
    await session.commit()

    await asyncio.to_thread(lambda: canvas_dir(canvas_id).mkdir(parents=True, exist_ok=True))

    return success_response(_canvas_to_dict(canvas))


@router.get("")
async def list_canvases(session: AsyncSession = Depends(get_db)):
    stmt = select(Canvas).order_by(Canvas.updated_at.desc())
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return success_response([_canvas_to_dict(c) for c in rows])


@router.get("/{canvas_id}")
async def get_canvas(canvas_id: str, session: AsyncSession = Depends(get_db)):
    canvas = await _get_canvas_or_404(canvas_id, session)
    return success_response(_canvas_to_dict(canvas))


@router.put("/{canvas_id}")
async def update_canvas(canvas_id: str, body: CanvasUpdateRequest, session: AsyncSession = Depends(get_db)):
    updates: dict[str, Any] = {"updated_at": datetime.utcnow()}
    if body.name is not None:
        updates["name"] = body.name
    if body.agent_id is not None:
        updates["agent_id"] = body.agent_id
    if body.chat_id is not None:
        updates["chat_id"] = body.chat_id
    if body.thumbnail is not None:
        updates["thumbnail"] = body.thumbnail

    stmt = update(Canvas).where(Canvas.id == canvas_id).values(**updates)
    result = await session.execute(stmt)
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return success_response({"id": canvas_id})


@router.delete("/{canvas_id}")
async def delete_canvas(canvas_id: str, session: AsyncSession = Depends(get_db)):
    stmt = delete(Canvas).where(Canvas.id == canvas_id)
    result = await session.execute(stmt)
    await session.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Canvas not found")

    cdir = canvas_dir(canvas_id)
    if cdir.exists():
        await asyncio.to_thread(shutil.rmtree, cdir, True)

    return success_response({"deleted": canvas_id})


# ── Snapshot ─────────────────────────────────────────────────────────


@router.put("/{canvas_id}/snapshot")
async def save_snapshot(canvas_id: str, body: SnapshotSaveRequest, session: AsyncSession = Depends(get_db)):
    await _get_canvas_or_404(canvas_id, session)

    snapshot_json = json.dumps(body.snapshot, ensure_ascii=False)
    if len(snapshot_json.encode("utf-8")) > MAX_SNAPSHOT_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Snapshot too large")

    await asyncio.to_thread(lambda: canvas_dir(canvas_id).mkdir(parents=True, exist_ok=True))
    await _write_file(snapshot_path(canvas_id), snapshot_json)

    updates: dict[str, Any] = {"updated_at": datetime.utcnow()}
    if body.thumbnail:
        updates["thumbnail"] = body.thumbnail
    await session.execute(update(Canvas).where(Canvas.id == canvas_id).values(**updates))
    await session.commit()

    _notify_canvas_change(canvas_id)

    return success_response({"saved": True})


@router.get("/{canvas_id}/snapshot")
async def load_snapshot(canvas_id: str, session: AsyncSession = Depends(get_db)):
    await _get_canvas_or_404(canvas_id, session)

    path = snapshot_path(canvas_id)
    if not path.exists():
        return success_response({"snapshot": None})

    content = await _read_file(path)
    return success_response({"snapshot": json.loads(content)})


# ── Selection ────────────────────────────────────────────────────────


@router.put("/{canvas_id}/selection")
async def save_selection(canvas_id: str, body: SelectionSaveRequest):
    await asyncio.to_thread(lambda: canvas_dir(canvas_id).mkdir(parents=True, exist_ok=True))

    payload = {
        "selectedShapes": body.selected_shapes,
        "updatedAt": datetime.utcnow().isoformat(),
    }
    await _write_file(selection_path(canvas_id), json.dumps(payload, ensure_ascii=False))

    return success_response({"saved": True})


@router.get("/{canvas_id}/selection")
async def load_selection(canvas_id: str):
    path = selection_path(canvas_id)
    if not path.exists():
        return success_response({"selectedShapes": [], "updatedAt": None})

    content = await _read_file(path)
    return success_response(json.loads(content))


# ── SSE ──────────────────────────────────────────────────────────────


@router.get("/{canvas_id}/events")
async def canvas_events(canvas_id: str, request: Request):
    """SSE endpoint for real-time canvas change notifications."""
    event = asyncio.Event()
    _sse_events.setdefault(canvas_id, set()).add(event)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    await asyncio.wait_for(event.wait(), timeout=30.0)
                    event.clear()
                    yield f"event: canvas-changed\ndata: {{}}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            bucket = _sse_events.get(canvas_id)
            if bucket is not None:
                bucket.discard(event)
                if not bucket:
                    _sse_events.pop(canvas_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_canvas_or_404(canvas_id: str, session: AsyncSession) -> Canvas:
    stmt = select(Canvas).where(Canvas.id == canvas_id)
    result = await session.execute(stmt)
    canvas = result.scalar_one_or_none()
    if not canvas:
        raise HTTPException(status_code=404, detail="Canvas not found")
    return canvas
