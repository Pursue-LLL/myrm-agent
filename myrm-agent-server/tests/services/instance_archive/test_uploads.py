"""Chunked upload sessions: geometry, resume, validation, path safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.instance_archive import ArchivePaths, UploadError, UploadStore


@pytest.fixture
def store(tmp_path: Path) -> UploadStore:
    return UploadStore(ArchivePaths(tmp_path))


def test_chunks_land_at_their_offset_in_any_order(store: UploadStore) -> None:
    payload = bytes(range(250)) * 4  # 1000 bytes
    session = store.create(len(payload), 300)  # 300 + 300 + 300 + 100
    assert session.chunk_count == 4
    for index in (3, 0, 2, 1):
        session = store.write_chunk(session.session_id, index, payload[index * 300 : (index + 1) * 300])

    assert session.complete
    assert store.archive_path(session.session_id).read_bytes() == payload


def test_resume_reports_received_chunks_after_reload(store: UploadStore) -> None:
    session = store.create(900, 300)
    store.write_chunk(session.session_id, 1, b"x" * 300)

    assert store.get(session.session_id).received == {1}
    assert not store.get(session.session_id).complete


@pytest.mark.parametrize(("index", "length"), [(0, 299), (0, 301), (3, 300), (-1, 300), (2, 301)])
def test_invalid_chunks_are_rejected(store: UploadStore, index: int, length: int) -> None:
    session = store.create(900, 300)

    with pytest.raises(UploadError) as rejected:
        store.write_chunk(session.session_id, index, b"x" * length)

    assert rejected.value.code == "invalid_chunk"


@pytest.mark.parametrize("size", [0, -5])
def test_invalid_geometry_is_rejected(store: UploadStore, size: int) -> None:
    with pytest.raises(UploadError) as rejected:
        store.create(size, 100)
    assert rejected.value.code == "invalid_geometry"
    with pytest.raises(UploadError):
        store.create(100, 64 * 1024 * 1024)


@pytest.mark.parametrize("session_id", ["../etc", "..", "abc", "g" * 32, ""])
def test_session_ids_cannot_escape_the_uploads_directory(store: UploadStore, session_id: str) -> None:
    with pytest.raises(UploadError) as rejected:
        store.get(session_id)
    assert rejected.value.code == "unknown_session"
    with pytest.raises(UploadError):
        store.discard(session_id)


def test_discard_removes_upload_and_staging(store: UploadStore, tmp_path: Path) -> None:
    session = store.create(100, 100)
    staging = ArchivePaths(tmp_path).staging / session.session_id
    staging.mkdir(parents=True)

    store.discard(session.session_id)

    assert not store.session_dir(session.session_id).exists()
    assert not staging.exists()
