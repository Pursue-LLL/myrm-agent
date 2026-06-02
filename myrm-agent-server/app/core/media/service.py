"""Media library service — CRUD, search, tagging for AI-generated media.

Persists generated images/videos/audio with rich metadata.
Storage is delegated to the existing StorageProvider (S3 or local FS),
while metadata lives in the SQLite media_library table for fast queries.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime

import nanoid
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import MediaLibrary

logger = logging.getLogger(__name__)

THUMBNAIL_MAX_SIZE = 256


class MediaQueryParams:
    """Parameters for querying the media library."""

    __slots__ = (
        "media_type",
        "tags",
        "keyword",
        "session_id",
        "batch_job_id",
        "before",
        "after",
        "cursor",
        "limit",
    )

    def __init__(
        self,
        *,
        media_type: str | None = None,
        tags: list[str] | None = None,
        keyword: str | None = None,
        session_id: str | None = None,
        batch_job_id: str | None = None,
        before: datetime | None = None,
        after: datetime | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> None:
        self.media_type = media_type
        self.tags = tags
        self.keyword = keyword
        self.session_id = session_id
        self.batch_job_id = batch_job_id
        self.before = before
        self.after = after
        self.cursor = cursor
        self.limit = min(limit, 100)


class MediaLibraryService:
    """Core service for the media gallery.

    Provides CRUD operations, search with cursor-based pagination,
    tag management, and thumbnail generation.
    """

    @staticmethod
    def _generate_id() -> str:
        return f"media_{nanoid.generate(size=12)}"

    async def save_media(
        self,
        session: AsyncSession,
        *,
        image_bytes: bytes,
        content_type: str = "image/png",
        prompt: str | None = None,
        model: str | None = None,
        resolution: str | None = None,
        source: str = "generate",
        session_id: str | None = None,
        batch_job_id: str | None = None,
        tags: list[str] | None = None,
    ) -> MediaLibrary:
        """Persist media bytes + metadata, generate thumbnail."""
        from app.platform_utils import get_storage_provider

        storage = get_storage_provider()
        media_id = self._generate_id()
        media_type = _detect_media_type(content_type)

        storage_key = f"media/sandbox/{media_id}.{_ext_from_mime(content_type)}"
        await storage.write(storage_key, image_bytes, content_type)

        thumbnail_key: str | None = None
        if media_type == "image":
            import asyncio

            thumbnail_key = f"media/sandbox/thumb_{media_id}.webp"
            thumb_bytes = await asyncio.to_thread(_generate_thumbnail, image_bytes)
            if thumb_bytes:
                await storage.write(thumbnail_key, thumb_bytes, "image/webp")
            else:
                thumbnail_key = None

        record = MediaLibrary(
            id=media_id,
            media_type=media_type,
            source=source,
            prompt=prompt,
            model=model,
            resolution=resolution,
            content_type=content_type,
            file_size=len(image_bytes),
            storage_key=storage_key,
            thumbnail_key=thumbnail_key,
            tags=tags or [],
            session_id=session_id,
            batch_job_id=batch_job_id,
        )
        session.add(record)
        await session.flush()
        logger.info("Media saved: %s (%s, %d bytes)", media_id, media_type, len(image_bytes))
        return record

    async def query(
        self,
        session: AsyncSession,
        params: MediaQueryParams,
    ) -> list[MediaLibrary]:
        """Query media with filtering, search, and cursor-based pagination."""
        stmt = select(MediaLibrary)

        if params.media_type:
            stmt = stmt.where(MediaLibrary.media_type == params.media_type)
        if params.session_id:
            stmt = stmt.where(MediaLibrary.session_id == params.session_id)
        if params.batch_job_id:
            stmt = stmt.where(MediaLibrary.batch_job_id == params.batch_job_id)
        if params.after:
            stmt = stmt.where(MediaLibrary.created_at >= params.after)
        if params.before:
            stmt = stmt.where(MediaLibrary.created_at <= params.before)
        if params.keyword:
            like_pattern = f"%{params.keyword}%"
            stmt = stmt.where(
                or_(
                    MediaLibrary.prompt.ilike(like_pattern),
                    MediaLibrary.model.ilike(like_pattern),
                )
            )
        if params.tags:
            for tag in params.tags:
                stmt = stmt.where(func.json_extract(MediaLibrary.tags, "$").like(f'%"{tag}"%'))
        if params.cursor:
            stmt = stmt.where(MediaLibrary.id < params.cursor)

        stmt = stmt.order_by(desc(MediaLibrary.created_at)).limit(params.limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(
        self,
        session: AsyncSession,
        media_id: str,
    ) -> MediaLibrary | None:
        """Get a single media item by ID."""
        stmt = select(MediaLibrary).where(
            MediaLibrary.id == media_id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_tags(
        self,
        session: AsyncSession,
        media_id: str,
        tags: list[str],
    ) -> MediaLibrary | None:
        """Replace the tag list for a media item."""
        item = await self.get_by_id(session, media_id)
        if item is None:
            return None
        item.tags = tags
        await session.flush()
        return item

    async def delete_media(
        self,
        session: AsyncSession,
        media_id: str,
    ) -> bool:
        """Delete media record and its storage files."""
        item = await self.get_by_id(session, media_id)
        if item is None:
            return False

        from app.platform_utils import get_storage_provider

        storage = get_storage_provider()
        for key in (item.storage_key, item.thumbnail_key):
            if key:
                try:
                    await storage.delete(key)
                except FileNotFoundError:
                    pass

        await session.delete(item)
        await session.flush()
        logger.info("Media deleted: %s", media_id)
        return True

    async def get_all_tags(
        self,
        session: AsyncSession,
    ) -> list[str]:
        """Get all unique tags for a user."""
        stmt = select(MediaLibrary.tags).where(
            MediaLibrary.tags.isnot(None),
        )
        result = await session.execute(stmt)
        tag_set: set[str] = set()
        for (tags_json,) in result:
            if isinstance(tags_json, list):
                tag_set.update(tags_json)
        return sorted(tag_set)

    async def count(
        self,
        session: AsyncSession,
    ) -> int:
        """Count total media items for a user."""
        stmt = select(func.count()).select_from(MediaLibrary).where()
        result = await session.execute(stmt)
        return result.scalar_one()

    async def batch_delete(
        self,
        session: AsyncSession,
        media_ids: list[str],
    ) -> int:
        """Delete multiple media items and their storage files."""
        stmt = select(MediaLibrary).where(
            MediaLibrary.id.in_(media_ids),
        )
        result = await session.execute(stmt)
        items = list(result.scalars().all())
        if not items:
            return 0

        from app.platform_utils import get_storage_provider

        storage = get_storage_provider()
        for item in items:
            for key in (item.storage_key, item.thumbnail_key):
                if key:
                    try:
                        await storage.delete(key)
                    except FileNotFoundError:
                        pass
            await session.delete(item)

        await session.flush()
        logger.info("Batch deleted %d media items", len(items))
        return len(items)

    async def batch_update_tags(
        self,
        session: AsyncSession,
        media_ids: list[str],
        tags: list[str],
    ) -> int:
        """Replace tags on multiple media items at once."""
        stmt = select(MediaLibrary).where(
            MediaLibrary.id.in_(media_ids),
        )
        result = await session.execute(stmt)
        items = list(result.scalars().all())
        for item in items:
            item.tags = tags
        await session.flush()
        if items:
            logger.info("Batch tagged %d media items with %s", len(items), tags)
        return len(items)


def _detect_media_type(content_type: str) -> str:
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("video/"):
        return "video"
    if content_type.startswith("audio/"):
        return "audio"
    return "other"


_MIME_EXT_MAP: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
}


def _ext_from_mime(content_type: str) -> str:
    return _MIME_EXT_MAP.get(content_type, "bin")


def _generate_thumbnail(image_bytes: bytes) -> bytes | None:
    """Generate a WebP thumbnail from image bytes.

    Returns None if PIL is unavailable or processing fails.
    Runs synchronously — callers should consider offloading for large images.
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((THUMBNAIL_MAX_SIZE, THUMBNAIL_MAX_SIZE), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=80)
        return buf.getvalue()
    except Exception:
        logger.debug("Thumbnail generation failed, skipping", exc_info=True)
        return None


media_library_service = MediaLibraryService()
