"""The ``media://<id>`` reference of a stored media item, and the loader that reads one back.

[INPUT]
- app.core.media.service::media_library_service (POS: media library record lookup)
- app.platform_utils::get_session_factory, get_storage_provider (POS: DB session factory and file storage singletons)

[OUTPUT]
- MEDIA_SCHEME: the scheme the input resolver registers the loader under
- MEDIA_REFERENCE_PREFIX: ``media://``
- media_reference(): media library record id -> ``media://<id>``
- parse_media_reference(): ``media://<id>`` -> record id
- read_media_reference(): record id -> the stored bytes

[POS]
The identity of every generated artifact: results, task payloads and chat messages hold ``media://<id>``, never a
storage URL (a ``file://`` URL is blocked by browsers, a signed URL expires). Everything that needs the bytes of a
reference reads them through here.
"""

from __future__ import annotations

from app.core.media.service import media_library_service
from app.platform_utils import get_session_factory, get_storage_provider

MEDIA_SCHEME = "media"
MEDIA_REFERENCE_PREFIX = f"{MEDIA_SCHEME}://"


def media_reference(media_id: str) -> str:
    """Reference string of the media library record ``media_id``."""
    return f"{MEDIA_REFERENCE_PREFIX}{media_id}"


def parse_media_reference(reference: str) -> str | None:
    """Record id of a ``media://<id>`` reference, ``None`` for any other string."""
    if not reference.startswith(MEDIA_REFERENCE_PREFIX):
        return None
    return reference.removeprefix(MEDIA_REFERENCE_PREFIX) or None


async def read_media_reference(media_id: str) -> bytes:
    """Bytes of the stored media item ``media_id``.

    Raises:
        LookupError: There is no media library record with this id.
        FileNotFoundError: The record exists but its file is gone from storage.
    """
    async with get_session_factory()() as session:
        item = await media_library_service.get_by_id(session, media_id)
    if item is None:
        raise LookupError(f"media {media_id} not found")
    return await get_storage_provider().read(item.storage_key)
