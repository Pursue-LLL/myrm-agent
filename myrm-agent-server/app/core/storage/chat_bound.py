"""Uploads that belong to a single chat, and the page images extracted from them.

[INPUT]
- app.core.storage.models::File (POS: file record carrying ``source_chat_id``)
- app.core.storage.service::FilesService (POS: file CRUD over the storage provider)
- app.core.storage.types::FilePurpose (POS: upload / generated split)

[OUTPUT]
- pdf_extract_source: the ``source_chat_id`` marker on the page images extracted from an upload
- chat_bound_uploads: the uploads that carry a chat binding
- derivatives_of: the page images extracted from the given uploads
- delete_uploads_with_derivatives: remove uploads together with their page images

[POS]
An upload normally outlives every chat, so its ``source_chat_id`` stays empty. A chat that must leave nothing
behind (web incognito) binds its uploads to itself; this module is the one place that knows how such an upload
and what was derived from it are found and removed. Selection is pure so the export, which reads sidecars off
disk, and the retention job, which lists through ``FilesService``, apply the same rule. Only incognito chats bind
uploads, so a binding by itself marks an upload as one that must neither be exported nor outlive its chat.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from app.core.storage.models import File
from app.core.storage.service import FilesService
from app.core.storage.types import FilePurpose

logger = logging.getLogger(__name__)

_PDF_EXTRACT_SOURCE_PREFIX = "pdf-extract-"


def pdf_extract_source(upload_id: str) -> str:
    """``source_chat_id`` of the page images persisted when ``upload_id`` is extracted."""
    return f"{_PDF_EXTRACT_SOURCE_PREFIX}{upload_id}"


def chat_bound_uploads(files: Iterable[File]) -> list[File]:
    """Uploads bound to a chat. Generated files keep their own expiry and are never selected."""
    return [file for file in files if file.purpose is FilePurpose.UPLOAD and file.source_chat_id]


def derivatives_of(uploads: Iterable[File], files: Iterable[File]) -> list[File]:
    """Page images in ``files`` that were extracted from one of ``uploads``."""
    markers = {pdf_extract_source(upload.id) for upload in uploads}
    return [file for file in files if file.purpose is FilePurpose.GENERATED and file.source_chat_id in markers]


async def delete_uploads_with_derivatives(service: FilesService, uploads: Sequence[File]) -> int:
    """Delete ``uploads`` and their page images; return how many files were removed.

    A file that cannot be removed is logged and skipped so one bad file never blocks the rest. Whatever is left
    is selected again by the next retention run.
    """
    if not uploads:
        return 0
    generated = await service.list_files(purpose=FilePurpose.GENERATED, include_expired=True)
    removed = 0
    for file in [*uploads, *derivatives_of(uploads, generated)]:
        try:
            removed += await service.delete_file(file.id)
        except Exception as exc:
            logger.warning("Chat-bound file removal failed (file=%s): %s", file.id, exc)
    return removed
