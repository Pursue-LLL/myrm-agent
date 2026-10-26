"""Stable item identity and raw path layout for ima items.

[INPUT]
- app.services.wiki.source_sync.publish_helpers::sanitize_path_segment (POS: byte-bounded path segment)

[OUTPUT]
- kb_item_key / note_item_key: ledger identity; NOTES_LANE
- build_raw_path: ``ima/<container>/<folders>/<title>-<suffix>.md`` within the raw gate's path budget

[POS]
ima reassigns ``media_id`` whenever a same-named file is replaced in place, so a knowledge-base item's
identity is the (kb, parent folder, title) tuple and ``media_id`` is only the version signal. Notes are
identified by their own id. Identity never depends on content, which keeps re-syncs idempotent.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import PurePosixPath

from app.services.wiki.source_sync.publish_helpers import sanitize_path_segment

NOTES_LANE = "notes"

_ROOT = "ima"
_MAX_FOLDER_DEPTH = 3
_CONTAINER_CHARS = 40
_FOLDER_CHARS = 30
_TITLE_CHARS = 60
_KNOWN_DOC_SUFFIXES = frozenset({".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".md", ".txt", ".html", ".epub"})
# Windows refuses these device names as a directory or file name, with or without an extension.
_WINDOWS_DEVICE_NAMES = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}
)


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]


def kb_item_key(kb_id: str, parent_folder_id: str, title: str) -> str:
    return f"kb_{_digest(kb_id, parent_folder_id, title)}"


def note_item_key(note_id: str) -> str:
    return f"note_{_digest(note_id)}"


def _segment(value: str, max_chars: int, fallback: str) -> str:
    cleaned = sanitize_path_segment(value)[:max_chars].strip("._-") or fallback
    return f"_{cleaned}" if cleaned.split(".", 1)[0].lower() in _WINDOWS_DEVICE_NAMES else cleaned


def _title_stem(title: str) -> str:
    path = PurePosixPath(title)
    return path.stem if path.suffix.lower() in _KNOWN_DOC_SUFFIXES else title


def build_raw_path(*, container: str, folders: Sequence[str], title: str, item_key: str) -> str:
    """Folder levels beyond ``_MAX_FOLDER_DEPTH`` are dropped from the path (the ledger keeps the full path).

    The short key suffix makes every path unique, so same-named items in different folders never collide.
    """
    parts = [_ROOT, _segment(container, _CONTAINER_CHARS, "library")]
    parts.extend(_segment(folder, _FOLDER_CHARS, "folder") for folder in folders[:_MAX_FOLDER_DEPTH])
    suffix = item_key.rsplit("_", 1)[-1][:8]
    parts.append(f"{_segment(_title_stem(title), _TITLE_CHARS, 'item')}-{suffix}.md")
    return "/".join(parts)
