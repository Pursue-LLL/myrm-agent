"""Registration helpers for the on-disk files a chat references.

[INPUT]
- app.core.storage.models::File (POS: file record)
- myrm_agent_harness.toolkits.storage.base::StorageProvider (POS: storage backend)

[OUTPUT]
- file_reference_lock: one lock per reference record, alive only while a registration holds or awaits it
- read_file_reference: the record stored at a metadata path, None when it is absent or unreadable

[POS]
Support for ``FilesService.save_file_reference``. A reference record sits at a key derived from (chat, real path),
so reading that key is how a file gets the same id on every registration. The lock covers the whole
read-then-write: without it two concurrent registrations of a file that has no record yet would each mint an id
and the file would end up as two artifacts. The lock is process-local, which holds because the server runs as a
single process (``run.py``); a multi-worker deployment would need a conditional write instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
import weakref

from myrm_agent_harness.toolkits.storage.base import StorageProvider

from app.core.storage.models import File

logger = logging.getLogger(__name__)

_REFERENCE_LOCKS: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def file_reference_lock(storage_path: str) -> asyncio.Lock:
    """Lock that serializes the registrations of the file whose record sits at *storage_path*."""
    return _REFERENCE_LOCKS.setdefault(storage_path, asyncio.Lock())


async def read_file_reference(storage: StorageProvider, metadata_path: str) -> File | None:
    """The record stored at *metadata_path*; None when there is none or it cannot be read.

    An unreadable record (a write cut short) counts as absent so the next registration replaces it; raising
    would make that file impossible to register for good.
    """
    try:
        record = File.from_dict(json.loads(await storage.read_text(metadata_path)))
    except FileNotFoundError:
        return None
    except (ValueError, AttributeError):
        logger.warning("Unreadable file reference record %s; it will be replaced", metadata_path)
        return None
    return record if record.id else None
