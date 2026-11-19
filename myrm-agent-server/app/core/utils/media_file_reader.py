"""Read stored media bytes for harness MediaResolver / VisionFallback.

[INPUT]
- app.core.storage paths and uploaded file metadata (POS: media upload storage)
- app.core.media.reference::parse_media_reference / read_media_reference (POS: ``media://<id>`` artifact identity and its loader)

[OUTPUT]
- read_media_content: loads the bytes behind a media key: a ``media://<id>`` generated-artifact reference or an uploaded file id (None when missing or unreadable)

[POS]
Server-side media byte loader shared by vision fallback and attachment flows.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def read_media_content(key: str) -> bytes | None:
    """Bytes of a generated artifact (``media://<id>``) or, for a bare id, of an uploaded file."""
    # Imported at call time: the media library and the storage services load the database layer, which a reader
    # that is only handed to the agent factory should not drag in when this module is imported.
    from app.core.media.reference import parse_media_reference, read_media_reference

    media_id = parse_media_reference(key)
    try:
        if media_id is not None:
            return await read_media_reference(media_id)
        from app.core.storage import files_service

        return await files_service.get_content(key)
    except (FileNotFoundError, LookupError):
        return None
    except Exception as exc:
        logger.warning("Failed to read media %s for vision resolve: %s", key, exc)
        return None
