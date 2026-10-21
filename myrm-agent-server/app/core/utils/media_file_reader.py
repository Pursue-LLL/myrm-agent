"""Read uploaded media bytes for harness MediaResolver / VisionFallback.

[INPUT]
- app.core.storage paths and uploaded file metadata (POS: media upload storage)

[OUTPUT]
- read_media_file_bytes: load bytes for vision/media pipelines

[POS]
Server-side media byte loader shared by vision fallback and attachment flows.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def read_uploaded_media_file_content(file_id: str) -> bytes | None:
    """Resolve ``/api/media/files/{file_id}/content`` via storage SSOT."""
    try:
        from app.core.storage import files_service

        return await files_service.get_content(file_id)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.warning(
            "Failed to read uploaded media file %s for vision resolve: %s",
            file_id,
            exc,
        )
        return None
