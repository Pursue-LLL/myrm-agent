"""The uploads of web incognito chats, and of chats that no longer exist, kept out of every export.

[INPUT]
- app.core.storage.chat_bound::chat_bound_uploads, derivatives_of (POS: which stored files belong to incognito chats)
- app.core.storage.models::File (POS: the sidecar record)
- app.core.storage.paths::FILES_ROOT_PREFIX, FILE_METADATA_SUFFIX (POS: where file sidecars sit)
- app.services.instance_archive.policy::StateScan (POS: the export's file list)

[OUTPUT]
- STORAGE_REL: where the file store sits below the state directory
- without_incognito_uploads: the scan minus the uploads bound to a chat the archive does not keep, their page images and their sidecars

[POS]
An upload outlives the chat it was sent in, and only the chat row names it. An incognito chat binds its uploads
to itself (``source_chat_id`` in the sidecar). Such an upload travels only if its chat is a chat the archive keeps:
one that is web incognito stays out with its messages, and so does one whose chat never got a row or is already
gone. The test is the chat's actual state rather than the binding alone, which keeps the rule correct on its own
terms: the client binds an upload only to a chat it starts incognito, and a chat's flag is fixed at its first
message because turning incognito on or off always starts a fresh chat. A sidecar that cannot be read takes its
file out and is reported as unreadable rather than guessed at.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable

from app.core.storage.chat_bound import chat_bound_uploads, derivatives_of
from app.core.storage.models import File
from app.core.storage.paths import FILE_METADATA_SUFFIX, FILES_ROOT_PREFIX
from app.services.instance_archive.policy import SourceFile, StateScan

STORAGE_REL = "storage"
_FILES_PREFIX = f"{STORAGE_REL}/{FILES_ROOT_PREFIX}/"


def without_incognito_uploads(scan: StateScan, surviving_chat_ids: Collection[str]) -> StateScan:
    """``scan`` without the uploads bound to a chat outside ``surviving_chat_ids``, their page images and sidecars."""
    records, unreadable = _read_sidecars(scan.sources)
    files = [record for _, record in records]
    private = [file for file in chat_bound_uploads(files) if file.source_chat_id not in surviving_chat_ids]
    private_ids = {file.id for file in [*private, *derivatives_of(private, files)]}
    private_sidecars = [sidecar for sidecar, record in records if record.id in private_ids]

    hidden = {rel for sidecar in [*private_sidecars, *unreadable] for rel in (sidecar, _content_rel(sidecar))}
    if not hidden:
        return scan
    carried = {source.rel for source in scan.sources}
    return StateScan(
        sources=[source for source in scan.sources if source.rel not in hidden],
        excluded=scan.excluded,
        unreadable=[
            *scan.unreadable,
            *(rel for sidecar in unreadable for rel in (sidecar, _content_rel(sidecar)) if rel in carried),
        ],
    )


def _read_sidecars(sources: Iterable[SourceFile]) -> tuple[list[tuple[str, File]], list[str]]:
    """The parsed sidecars by state-directory-relative path, and the sidecars that could not be read."""
    records: list[tuple[str, File]] = []
    unreadable: list[str] = []
    for source in sources:
        if not (source.rel.startswith(_FILES_PREFIX) and source.rel.endswith(FILE_METADATA_SUFFIX)):
            continue
        try:
            record = _parse(source.path.read_bytes())
        except OSError:
            unreadable.append(source.rel)
            continue
        if record is not None:
            records.append((source.rel, record))
    return records, unreadable


def _content_rel(sidecar_rel: str) -> str:
    return sidecar_rel.removesuffix(FILE_METADATA_SUFFIX)


def _parse(raw: bytes) -> File | None:
    """The record of a sidecar, or ``None`` for one the application itself would skip."""
    try:
        data = json.loads(raw)
        return File.from_dict(data) if isinstance(data, dict) else None
    except ValueError:
        return None
