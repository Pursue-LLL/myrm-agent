"""Media gallery API: list, search, tag, serve and delete media items.

[INPUT]
- app.core.media.service::media_library_service, MediaQueryParams (POS: media library records and their write path)
- app.platform_utils::get_storage_provider (POS: process-wide file storage behind a record's storage key)
- app.api.dependencies::get_db_session (POS: request-scoped DB session)

[OUTPUT]
- router: ``/media`` routes: cursor-paginated listing with type, tag, keyword, session and time filters, the tag list,
  batch delete and batch tag replace, one item, its file (HTTP range requests), its 256px thumbnail, tag update, delete

[POS]
The HTTP door to the media library. ``/{media_id}/file`` is where a ``media://<id>`` reference ends up in the browser,
so it answers range requests (video and audio cannot seek or play in Safari without them) and carries a cache header
that never expires, since the bytes behind an id never change.
"""

from __future__ import annotations

import logging
from datetime import datetime

from anyio import to_thread
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.media.service import MediaQueryParams, media_library_service
from app.database.models import MediaLibrary
from app.platform_utils import get_storage_provider

logger = logging.getLogger(__name__)
router = APIRouter()

# The bytes behind a media id never change, so a client may keep its copy for good.
_IMMUTABLE_CACHE_CONTROL = "private, max-age=31536000, immutable"


class MediaItemResponse(BaseModel):
    """Single media item in API responses."""

    id: str
    media_type: str
    source: str
    prompt: str | None = None
    model: str | None = None
    resolution: str | None = None
    content_type: str
    file_size: int
    tags: list[str] = Field(default_factory=list)
    session_id: str | None = None
    thumbnail_url: str | None = None
    created_at: datetime


class MediaListResponse(BaseModel):
    """Paginated media list response."""

    items: list[MediaItemResponse]
    next_cursor: str | None = None
    total: int


class UpdateTagsRequest(BaseModel):
    """Request body for updating tags."""

    tags: list[str]


def _to_response(item: "MediaLibrary", api_prefix: str = "/api/v1") -> MediaItemResponse:
    """Convert DB model to API response."""

    thumb_url = f"{api_prefix}/media/{item.id}/thumbnail" if item.thumbnail_key else None
    return MediaItemResponse(
        id=item.id,
        media_type=item.media_type,
        source=item.source,
        prompt=item.prompt,
        model=item.model,
        resolution=item.resolution,
        content_type=item.content_type,
        file_size=item.file_size,
        tags=item.tags or [],
        session_id=item.session_id,
        thumbnail_url=thumb_url,
        created_at=item.created_at,
    )


@router.get("/", response_model=MediaListResponse)
async def list_media(
    db: AsyncSession = Depends(get_db_session),
    media_type: str | None = Query(None, description="Filter by type: image/video/audio"),
    tags: str | None = Query(None, description="Comma-separated tags to filter by"),
    keyword: str | None = Query(None, description="Search prompt or model name"),
    session_id: str | None = Query(None),
    before: datetime | None = Query(None),
    after: datetime | None = Query(None),
    cursor: str | None = Query(None, description="Cursor for pagination (media ID)"),
    limit: int = Query(20, ge=1, le=100),
) -> MediaListResponse:
    """List media with filtering, search, and cursor-based pagination."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    params = MediaQueryParams(
        media_type=media_type,
        tags=tag_list,
        keyword=keyword,
        session_id=session_id,
        before=before,
        after=after,
        cursor=cursor,
        limit=limit,
    )

    items = await media_library_service.query(db, params)
    total = await media_library_service.count(db)
    next_cursor = items[-1].id if len(items) == limit else None

    return MediaListResponse(
        items=[_to_response(item) for item in items],
        next_cursor=next_cursor,
        total=total,
    )


@router.get("/tags", response_model=list[str])
async def list_tags(
    db: AsyncSession = Depends(get_db_session),
) -> list[str]:
    """Get all unique tags for the current user."""
    return await media_library_service.get_all_tags(db)


class BatchIdsRequest(BaseModel):
    """Request body with a list of media IDs."""

    ids: list[str] = Field(..., min_length=1, max_length=100)


class BatchTagsRequest(BaseModel):
    """Request body for batch tag update."""

    ids: list[str] = Field(..., min_length=1, max_length=100)
    tags: list[str]


# Declared before the ``/{media_id}`` routes on purpose: a route matches in declaration order, so
# ``PUT /batch/tags`` placed after ``PUT /{media_id}/tags`` would be taken for the tags of a media item named ``batch``.
@router.post("/batch/delete")
async def batch_delete_media(
    body: BatchIdsRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    """Delete multiple media items at once."""
    count = await media_library_service.batch_delete(db, body.ids)
    await db.commit()
    return {"deleted": count}


@router.put("/batch/tags")
async def batch_update_tags(
    body: BatchTagsRequest,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, int]:
    """Update tags for multiple media items at once."""
    count = await media_library_service.batch_update_tags(db, body.ids, body.tags)
    await db.commit()
    return {"updated": count}


@router.get("/{media_id}", response_model=MediaItemResponse)
async def get_media(
    media_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> MediaItemResponse:
    """Get a single media item by ID."""
    item = await media_library_service.get_by_id(db, media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media not found")
    return _to_response(item)


@router.get("/{media_id}/file")
async def serve_media_file(
    media_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Serve the original media file.

    A file on the local disk is streamed by the server, which answers HTTP range requests: browsers cannot seek a
    video or audio element otherwise, and Safari will not play one at all. Remote storage is read whole.
    """
    item = await media_library_service.get_by_id(db, media_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Media not found")

    ext = item.storage_key.rsplit(".", 1)[-1] if "." in item.storage_key else "bin"
    filename = f"{item.id}.{ext}"
    storage = get_storage_provider()
    local_path = storage.local_path(item.storage_key)
    if local_path is not None:
        if not await to_thread.run_sync(local_path.is_file):
            raise HTTPException(status_code=404, detail="Media file not found in storage")
        return FileResponse(
            local_path,
            media_type=item.content_type,
            filename=filename,
            content_disposition_type="inline",
            headers={"Cache-Control": _IMMUTABLE_CACHE_CONTROL},
        )

    try:
        content = await storage.read(item.storage_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Media file not found in storage") from None
    return Response(
        content=content,
        media_type=item.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": _IMMUTABLE_CACHE_CONTROL,
        },
    )


@router.get("/{media_id}/thumbnail")
async def serve_thumbnail(
    media_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Serve the thumbnail version (256px WebP)."""
    item = await media_library_service.get_by_id(db, media_id)
    if item is None or not item.thumbnail_key:
        raise HTTPException(status_code=404, detail="Thumbnail not found")

    storage = get_storage_provider()
    try:
        content = await storage.read(item.thumbnail_key)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Thumbnail file not found") from None
    return Response(content=content, media_type="image/webp")


@router.put("/{media_id}/tags", response_model=MediaItemResponse)
async def update_tags(
    media_id: str,
    body: UpdateTagsRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MediaItemResponse:
    """Update tags for a media item."""
    item = await media_library_service.update_tags(db, media_id, body.tags)
    if item is None:
        raise HTTPException(status_code=404, detail="Media not found")
    await db.commit()
    return _to_response(item)


@router.delete("/{media_id}")
async def delete_media(
    media_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, bool]:
    """Delete a media item and its storage files."""
    deleted = await media_library_service.delete_media(db, media_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Media not found")
    await db.commit()
    return {"deleted": True}
