"""Versioned, byte-exact text editing for the workspace file editor.

[INPUT]
- myrm_agent_harness.infra.atomic_write::atomic_write (POS: crash-safe file replace)
- hashlib / os / threading / weakref (stdlib)

[OUTPUT]
- EDITABLE_MAX_BYTES: size above which a file is shown read-only
- read_text_snapshot: decode a file for editing together with its content version
- write_text_if_version: compare-and-swap save that keeps line endings, BOM and permissions
- create_text_file_exclusive: create a new text file and never overwrite
- text_style_of: line-ending / BOM style of an existing file
- VersionConflict / NotEditable / InvalidContent / WriteBlocked: save outcomes for the API layer

[POS]
Business-layer I/O behind the human editor of the workspace file browser. The agent has read, full-read
and version gates (FileIntegrityGuard); this gives the editor the same guarantee: a save is refused when
the file changed since it was read, and everything the user did not touch stays byte-identical (line
endings, BOM, permissions). Files the editor cannot round-trip exactly are read-only. No HTTP types.
"""

from __future__ import annotations

import codecs
import contextlib
import hashlib
import os
import stat
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Final, Literal

from myrm_agent_harness.infra.atomic_write import atomic_write

EDITABLE_MAX_BYTES: Final = 1024 * 1024

type ReadonlyReason = Literal["binary", "not_utf8", "mixed_line_endings", "too_large"]
type LineEnding = Literal["lf", "crlf"]
type ContentIssue = Literal["contains_nul", "not_utf8", "too_large"]

_BOM: Final = b"\xef\xbb\xbf"
# Windows may hold a file open for a moment (antivirus scan, preview handle); POSIX never needs the retry.
_RETRY_ON_PERMISSION_ERROR: Final = os.name == "nt"
_REPLACE_ATTEMPTS: Final = 5
_REPLACE_RETRY_DELAY_S: Final = 0.05


@dataclass(frozen=True, slots=True)
class TextStyle:
    line_ending: LineEnding = "lf"
    has_bom: bool = False


@dataclass(frozen=True, slots=True)
class TextSnapshot:
    content: str  # LF line endings, no BOM; only a prefix when ``truncated``
    version: str  # sha256 of the raw bytes; empty when the file was too large to hash
    size: int
    style: TextStyle
    readonly_reason: ReadonlyReason | None
    truncated: bool

    @property
    def editable(self) -> bool:
        return self.readonly_reason is None


@dataclass(frozen=True, slots=True)
class WriteOutcome:
    version: str
    size: int
    changed: bool


class TextEditError(Exception):
    """Base class of the save outcomes the API layer turns into responses."""


class VersionConflict(TextEditError):
    """The file on disk is no longer the version the editor started from."""

    def __init__(self, current_version: str) -> None:
        super().__init__("file changed since it was read")
        self.current_version = current_version


class NotEditable(TextEditError):
    """The file on disk cannot be edited without altering bytes the user never saw."""

    def __init__(self, reason: ReadonlyReason) -> None:
        super().__init__(f"file is read-only: {reason}")
        self.reason = reason


class InvalidContent(TextEditError):
    """The submitted text cannot be stored as an editable text file."""

    def __init__(self, issue: ContentIssue) -> None:
        super().__init__(f"content rejected: {issue}")
        self.issue = issue


class WriteBlocked(TextEditError):
    """The operating system refused the write (read-only file, permissions, file in use)."""


@dataclass(frozen=True, slots=True)
class _Decoded:
    text: str
    style: TextStyle
    reason: ReadonlyReason | None


_path_locks: weakref.WeakValueDictionary[str, threading.Lock] = weakref.WeakValueDictionary()
_path_locks_guard = threading.Lock()


def _lock_for(path: str) -> threading.Lock:
    """Per-path lock serialising this process's own saves; entries vanish once nobody holds them."""
    with _path_locks_guard:
        lock = _path_locks.get(path)
        if lock is None:
            lock = threading.Lock()
            _path_locks[path] = lock
        return lock


def version_of(raw: bytes) -> str:
    """Content version token: sha256 of the raw bytes (immune to touch / mtime-only changes)."""
    return hashlib.sha256(raw).hexdigest()


def _line_ending_of(text: str) -> LineEnding | None:
    """Line-ending style of ``text``; ``None`` when styles are mixed or a lone CR is present."""
    crlf = text.count("\r\n")
    lone_cr = text.count("\r") - crlf
    lone_lf = text.count("\n") - crlf
    if lone_cr or (crlf and lone_lf):
        return None
    return "crlf" if crlf else "lf"


def _classify(raw: bytes, *, partial: bool = False) -> _Decoded:
    """Decode ``raw`` for display and decide whether it can be edited byte-exactly.

    ``partial`` marks a prefix of a larger file, where a multi-byte character cut at the end is not an error.
    """
    if b"\x00" in raw:
        return _Decoded("", TextStyle(), "binary")
    has_bom = raw.startswith(_BOM)
    body = raw[len(_BOM) :] if has_bom else raw
    valid_utf8 = True
    if partial:
        text = codecs.getincrementaldecoder("utf-8")("replace").decode(body)
    else:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text, valid_utf8 = body.decode("utf-8", errors="replace"), False
    line_ending = _line_ending_of(text)
    reason: ReadonlyReason | None = None
    if not valid_utf8:
        reason = "not_utf8"
    elif line_ending is None:
        reason = "mixed_line_endings"
    display = text.replace("\r\n", "\n").replace("\r", "\n")
    return _Decoded(display, TextStyle(line_ending or "lf", has_bom), reason)


def read_text_snapshot(path: str) -> TextSnapshot:
    """Read ``path`` for the editor; ``OSError`` (missing file, permissions) propagates unchanged.

    The size is checked while reading, so an oversized file is never hashed or decoded beyond its first
    ``EDITABLE_MAX_BYTES``; such a file is shown as a read-only preview.
    """
    with open(path, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        raw = handle.read(EDITABLE_MAX_BYTES + 1)
    truncated = len(raw) > EDITABLE_MAX_BYTES
    if truncated:
        raw = raw[:EDITABLE_MAX_BYTES]
    decoded = _classify(raw, partial=truncated)
    reason = "too_large" if truncated and decoded.reason != "binary" else decoded.reason
    return TextSnapshot(
        content=decoded.text,
        version="" if truncated else version_of(raw),
        size=size,
        style=decoded.style,
        readonly_reason=reason,
        truncated=truncated,
    )


def text_style_of(path: str) -> TextStyle:
    """Line-ending / BOM style of an existing file; LF without BOM when it is not editable text."""
    try:
        snapshot = read_text_snapshot(path)
    except OSError:
        return TextStyle()
    return snapshot.style if snapshot.editable else TextStyle()


def _encode(text: str, style: TextStyle) -> bytes:
    """Encode edited text in the file's own line-ending and BOM style (the editor works with LF only)."""
    if "\x00" in text:
        raise InvalidContent("contains_nul")
    body = text.replace("\r\n", "\n").replace("\r", "\n")
    if style.line_ending == "crlf":
        body = body.replace("\n", "\r\n")
    try:
        data = body.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise InvalidContent("not_utf8") from exc
    if style.has_bom:
        data = _BOM + data
    if len(data) > EDITABLE_MAX_BYTES:
        # A file this large would open read-only next time; refuse instead of locking the user out.
        raise InvalidContent("too_large")
    return data


def _read_current_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        raw = handle.read(EDITABLE_MAX_BYTES + 1)
    if len(raw) > EDITABLE_MAX_BYTES:
        raise NotEditable("too_large")
    return raw


def _replace(path: str, data: bytes) -> None:
    """Atomically replace ``path`` with ``data`` keeping its permission bits."""
    # A rename would replace a read-only file without complaint; an in-place write never did.
    if not os.access(path, os.W_OK):
        raise WriteBlocked("file is read-only")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            atomic_write(path, data, mode=mode)
            return
        except PermissionError as exc:
            if not _RETRY_ON_PERMISSION_ERROR or attempt == _REPLACE_ATTEMPTS - 1:
                raise WriteBlocked(str(exc)) from exc
            time.sleep(_REPLACE_RETRY_DELAY_S)


def write_text_if_version(path: str, text: str, base_version: str) -> WriteOutcome:
    """Save ``text`` over ``path`` only when the file still has ``base_version``.

    There is no unconditional write: overwriting after a conflict means reading the current version first and
    saving against it. An unchanged result is not written at all, so timestamps and file watchers stay quiet.
    Writers outside this process are detected by the version check; the span between that check and the
    rename is the only window they can slip through.
    """
    with _lock_for(path):
        raw = _read_current_bytes(path)
        current = version_of(raw)
        if current != base_version:
            raise VersionConflict(current)
        decoded = _classify(raw)
        if decoded.reason is not None:
            raise NotEditable(decoded.reason)
        data = _encode(text, decoded.style)
        if data == raw:
            return WriteOutcome(current, len(raw), changed=False)
        _replace(path, data)
        return WriteOutcome(version_of(data), len(data), changed=True)


def create_text_file_exclusive(path: str, text: str, style: TextStyle) -> WriteOutcome:
    """Create ``path`` holding ``text``; ``FileExistsError`` when the name is taken, never an overwrite."""
    data = _encode(text, style)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, 0o666)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(path)
        raise
    return WriteOutcome(version_of(data), len(data), changed=True)
