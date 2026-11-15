"""The ``media://<id>`` reference of a stored media item, and the loader that reads one back."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.core.media.reference import (
    MEDIA_REFERENCE_PREFIX,
    MEDIA_SCHEME,
    media_reference,
    parse_media_reference,
    read_media_reference,
)
from tests.support.media_library_env import MediaLibraryEnv, media_library_env

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


@pytest.fixture
async def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MediaLibraryEnv]:
    async with media_library_env(tmp_path / "storage", monkeypatch) as env:
        yield env


def test_the_scheme_and_the_prefix_agree() -> None:
    assert MEDIA_REFERENCE_PREFIX == f"{MEDIA_SCHEME}://"


def test_a_reference_round_trips_its_record_id() -> None:
    assert media_reference("media_abc123") == "media://media_abc123"
    assert parse_media_reference(media_reference("media_abc123")) == "media_abc123"


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "media://",
        "media:/media_abc",
        "MEDIA://media_abc",
        "file:///tmp/a.png",
        "https://x.test/a.png",
        "/api/v1/media/m/file",
    ],
)
def test_anything_but_a_media_reference_has_no_record_id(reference: str) -> None:
    assert parse_media_reference(reference) is None


async def test_the_loader_returns_the_stored_bytes(library: MediaLibraryEnv) -> None:
    record = await library.store(_PNG)

    assert await read_media_reference(record.id) == _PNG


async def test_the_loader_raises_for_an_id_the_library_does_not_hold(library: MediaLibraryEnv) -> None:
    await library.store(_PNG)

    with pytest.raises(LookupError, match="media_gone"):
        await read_media_reference("media_gone")


async def test_the_loader_raises_when_the_record_outlives_its_file(library: MediaLibraryEnv) -> None:
    record = await library.store(_PNG)
    await library.storage.delete(record.storage_key)

    with pytest.raises(FileNotFoundError):
        await read_media_reference(record.id)
