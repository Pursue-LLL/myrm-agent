"""Shared media library persistence callback for image generation.

[INPUT]
- myrm_agent_harness.toolkits.llms.image.models::MediaCallback, MediaMeta (POS: callback contract)
- app.core.media.service::media_library_service (POS: DB + storage persist)

[OUTPUT]
- create_media_persist_callback(): async callback saving generated images to media library

[POS]
Sync/async image generation shared persist hook used by tool_setup and worker resolver.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.llms.image.models import MediaCallback, MediaMeta

logger = logging.getLogger(__name__)


def create_media_persist_callback(
    *,
    chat_id: str | None,
    model_name: str | None,
    source: str,
) -> MediaCallback | None:
    """Build async callback that saves generated images to the media library."""
    if not chat_id or not chat_id.strip():
        return None

    session_id = chat_id.strip()

    async def _persist(
        media_bytes: bytes,
        mime_type: str,
        meta: MediaMeta,
    ) -> str:
        try:
            from app.core.media.service import media_library_service
            from app.platform_utils import get_session_factory, get_storage_provider

            storage = get_storage_provider()
            factory = get_session_factory()

            async with factory() as session:
                record = await media_library_service.save_media(
                    session,
                    image_bytes=media_bytes,
                    content_type=mime_type,
                    prompt=meta.prompt,
                    model=meta.model or model_name,
                    resolution=meta.resolution,
                    source=source,
                    session_id=session_id,
                )
                await session.commit()
                url = await storage.get_url(record.storage_key)
                return str(url)
        except Exception:
            logger.warning(
                "Media persist failed (source=%s, non-blocking)",
                source,
                exc_info=True,
            )
            return ""

    return _persist


__all__ = ["create_media_persist_callback"]
