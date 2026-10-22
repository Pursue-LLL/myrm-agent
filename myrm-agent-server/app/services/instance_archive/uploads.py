"""Resumable chunked upload sessions for instance archives.

[INPUT]
- app.services.instance_archive.models::ArchivePaths (POS: working layout)
- myrm_agent_harness.infra.state_archive::ensure_free_space (POS: disk preflight)

[OUTPUT]
- UploadSession: size, chunk geometry and received chunks of one upload
- UploadStore: create / write_chunk / get / discard
- UploadError: stable machine-readable rejection

[POS]
Archives exceed the request-body limit (server 15 MB, control-plane proxy
buffers requests), so the browser sends fixed-size chunks that are written
at their offset into one preallocated file: no concatenation pass, no second
copy on disk, and an interrupted upload resumes by asking which chunks exist.
"""

from __future__ import annotations

import re
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.infra.state_archive import InsufficientSpaceError, ensure_free_space

from app.services.instance_archive.models import ArchivePaths, read_json, write_json_atomic

MAX_CHUNK_BYTES = 8 * 1024 * 1024
_SESSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
ARCHIVE_FILE = "archive.zip"
_SESSION_FILE = "session.json"


class UploadError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(slots=True)
class UploadSession:
    session_id: str
    size_bytes: int
    chunk_bytes: int
    created_at: str
    received: set[int] = field(default_factory=set)
    state: str = "uploading"  # uploading | staged | confirmed
    report: dict[str, object] | None = None

    @property
    def chunk_count(self) -> int:
        return -(-self.size_bytes // self.chunk_bytes)

    @property
    def complete(self) -> bool:
        return len(self.received) == self.chunk_count

    def to_json(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "size_bytes": self.size_bytes,
            "chunk_bytes": self.chunk_bytes,
            "created_at": self.created_at,
            "received": sorted(self.received),
            "state": self.state,
            "report": self.report,
        }


class UploadStore:
    def __init__(self, paths: ArchivePaths) -> None:
        self._paths = paths
        self._lock = threading.Lock()

    def session_dir(self, session_id: str) -> Path:
        if not _SESSION_ID_RE.fullmatch(session_id):
            raise UploadError("unknown_session", "Unknown upload session")
        return self._paths.uploads / session_id

    def archive_path(self, session_id: str) -> Path:
        return self.session_dir(session_id) / ARCHIVE_FILE

    def create(self, size_bytes: int, chunk_bytes: int) -> UploadSession:
        if size_bytes <= 0 or not 0 < chunk_bytes <= MAX_CHUNK_BYTES:
            raise UploadError("invalid_geometry", "Invalid upload size or chunk size")
        try:
            self._paths.uploads.mkdir(parents=True, exist_ok=True)
            ensure_free_space(self._paths.uploads, size_bytes)
        except InsufficientSpaceError as exc:
            raise UploadError("insufficient_space", "Not enough free disk space for this archive") from exc
        session = UploadSession(
            session_id=uuid.uuid4().hex,
            size_bytes=size_bytes,
            chunk_bytes=chunk_bytes,
            created_at=datetime.now(UTC).isoformat(),
        )
        directory = self.session_dir(session.session_id)
        directory.mkdir(parents=True)
        with (directory / ARCHIVE_FILE).open("wb") as handle:
            handle.truncate(size_bytes)
        self.save(session)
        return session

    def save(self, session: UploadSession) -> None:
        write_json_atomic(self.session_dir(session.session_id) / _SESSION_FILE, session.to_json())

    def get(self, session_id: str) -> UploadSession:
        raw = read_json(self.session_dir(session_id) / _SESSION_FILE)
        if raw is None:
            raise UploadError("unknown_session", "Unknown upload session")
        try:
            received = raw["received"]
            report = raw.get("report")
            if not isinstance(received, list) or not (report is None or isinstance(report, dict)):
                raise TypeError
            return UploadSession(
                session_id=str(raw["session_id"]),
                size_bytes=int(str(raw["size_bytes"])),
                chunk_bytes=int(str(raw["chunk_bytes"])),
                created_at=str(raw["created_at"]),
                received={int(i) for i in received},
                state=str(raw["state"]),
                report=report,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UploadError("unknown_session", "Unknown upload session") from exc

    def write_chunk(self, session_id: str, index: int, data: bytes) -> UploadSession:
        with self._lock:
            session = self.get(session_id)
            if session.state != "uploading":
                raise UploadError("not_uploading", "This upload is no longer accepting chunks")
            if not 0 <= index < session.chunk_count:
                raise UploadError("invalid_chunk", "Chunk index out of range")
            expected = min(session.chunk_bytes, session.size_bytes - index * session.chunk_bytes)
            if len(data) != expected:
                raise UploadError("invalid_chunk", "Chunk has an unexpected length")
            with self.archive_path(session_id).open("r+b") as handle:
                handle.seek(index * session.chunk_bytes)
                handle.write(data)
            session.received.add(index)
            self.save(session)
            return session

    def discard(self, session_id: str) -> None:
        shutil.rmtree(self.session_dir(session_id), ignore_errors=True)
        shutil.rmtree(self._paths.staging / session_id, ignore_errors=True)
