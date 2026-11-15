"""Media library persistence callback shared by the image, video and TTS engines.

[INPUT]
- app.core.media.service::media_library_service (POS: DB + storage persist)
- app.core.media.reference::media_reference (POS: ``media://<id>`` artifact identity)
- app.platform_utils::get_session_factory (POS: DB session factory)

[OUTPUT]
- GeneratedMediaMeta: the metadata fields of the engines' ``MediaMeta`` classes that the media library stores
- create_media_persist_callback(): async callback that stores generated media and returns its ``media://`` reference

[POS]
The business-layer half of the engines' fail-closed persistence contract: every generated image, video or audio is
stored in the media library whether or not a chat is involved (background jobs have none), and the callback raises
when it cannot store it, so the engine fails the generation instead of reporting an artifact nobody can reach.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from app.core.media.reference import media_reference
from app.core.media.service import media_library_service
from app.platform_utils import get_session_factory


class GeneratedMediaMeta(Protocol):
    """Metadata an engine passes with the bytes; image, video and TTS each define a class with these fields."""

    @property
    def prompt(self) -> str | None: ...

    @property
    def model(self) -> str | None: ...


PersistCallback = Callable[[bytes, str, GeneratedMediaMeta], Awaitable[str]]


def create_media_persist_callback(
    *,
    chat_id: str | None,
    model_name: str | None,
    source: str,
) -> PersistCallback:
    """Build the async callback that stores generated media and returns its ``media://<id>`` reference.

    ``chat_id`` only links the record to its conversation; background jobs pass ``None`` and are stored all the same.
    """
    session_id = chat_id.strip() if chat_id and chat_id.strip() else None

    async def _persist(media_bytes: bytes, mime_type: str, meta: GeneratedMediaMeta) -> str:
        async with get_session_factory()() as session:
            record = await media_library_service.save_media(
                session,
                image_bytes=media_bytes,
                content_type=mime_type,
                prompt=meta.prompt,
                model=meta.model or model_name,
                # Only image and video results know their resolution; audio has none.
                resolution=getattr(meta, "resolution", None),
                source=source,
                session_id=session_id,
            )
            await session.commit()
            return media_reference(record.id)

    return _persist


__all__ = ["GeneratedMediaMeta", "PersistCallback", "create_media_persist_callback"]
