"""``/media``: the file endpoint serves bytes from disk with range support and caching; the batch routes still work."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.media_library_env import MediaLibraryEnv, media_library_env
from tests.support.minimal_app import API_PREFIX, build_minimal_app

_IMMUTABLE = "private, max-age=31536000, immutable"
# Every offset holds a different byte value within a block, so a wrong slice cannot pass by accident.
_VIDEO = bytes(range(256)) * 400
_MP4 = "video/mp4"


@pytest.fixture
async def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MediaLibraryEnv]:
    async with media_library_env(tmp_path / "storage", monkeypatch) as env:
        yield env


@pytest.fixture
async def client(library: MediaLibraryEnv) -> AsyncIterator[AsyncClient]:
    app = build_minimal_app("media")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http


def _file_url(media_id: str) -> str:
    return f"{API_PREFIX}/media/{media_id}/file"


async def test_the_file_comes_with_its_type_a_name_and_a_cache_header_that_never_expires(
    library: MediaLibraryEnv, client: AsyncClient
) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)

    response = await client.get(_file_url(record.id))

    assert response.status_code == 200
    assert response.content == _VIDEO
    assert response.headers["content-type"] == _MP4
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == _IMMUTABLE
    assert response.headers["content-disposition"] == f'inline; filename="{record.id}.mp4"'


async def test_a_range_request_gets_exactly_that_slice(library: MediaLibraryEnv, client: AsyncClient) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)

    response = await client.get(_file_url(record.id), headers={"Range": "bytes=1000-1999"})

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 1000-1999/{len(_VIDEO)}"
    assert response.content == _VIDEO[1000:2000]
    assert response.headers["cache-control"] == _IMMUTABLE


async def test_the_probe_a_browser_sends_before_playing_is_answered_with_two_bytes(
    library: MediaLibraryEnv, client: AsyncClient
) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)

    response = await client.get(_file_url(record.id), headers={"Range": "bytes=0-1"})

    assert response.status_code == 206
    assert response.content == _VIDEO[:2]


async def test_an_open_ended_range_runs_to_the_end_of_the_file(library: MediaLibraryEnv, client: AsyncClient) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)
    start = len(_VIDEO) - 2400

    response = await client.get(_file_url(record.id), headers={"Range": f"bytes={start}-"})

    assert response.status_code == 206
    assert response.content == _VIDEO[start:]


async def test_a_range_past_the_end_of_the_file_is_refused(library: MediaLibraryEnv, client: AsyncClient) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)

    response = await client.get(_file_url(record.id), headers={"Range": f"bytes={len(_VIDEO) + 10}-"})

    assert response.status_code == 416


async def test_an_unknown_id_is_not_found(library: MediaLibraryEnv, client: AsyncClient) -> None:
    await library.store(_VIDEO, content_type=_MP4)

    response = await client.get(_file_url("media_gone"))

    assert response.status_code == 404


async def test_a_record_whose_file_is_gone_from_disk_is_not_found(library: MediaLibraryEnv, client: AsyncClient) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)
    await library.storage.delete(record.storage_key)

    response = await client.get(_file_url(record.id))

    assert response.status_code == 404


async def test_storage_without_a_local_path_is_read_whole_with_the_same_headers(
    library: MediaLibraryEnv, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)
    monkeypatch.setattr(library.storage, "local_path", lambda key: None)

    response = await client.get(_file_url(record.id))

    assert response.status_code == 200
    assert response.content == _VIDEO
    assert response.headers["content-type"] == _MP4
    assert response.headers["cache-control"] == _IMMUTABLE
    assert response.headers["content-disposition"] == f'inline; filename="{record.id}.mp4"'


async def test_storage_without_a_local_path_reports_a_missing_file_as_not_found(
    library: MediaLibraryEnv, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = await library.store(_VIDEO, content_type=_MP4)
    await library.storage.delete(record.storage_key)
    monkeypatch.setattr(library.storage, "local_path", lambda key: None)

    response = await client.get(_file_url(record.id))

    assert response.status_code == 404


async def test_batch_delete_removes_the_items_and_their_files_and_counts_only_the_ones_it_found(
    library: MediaLibraryEnv, client: AsyncClient
) -> None:
    first = await library.store(_VIDEO, content_type=_MP4)
    second = await library.store(_VIDEO, content_type=_MP4)
    kept = await library.store(_VIDEO, content_type=_MP4)

    response = await client.post(f"{API_PREFIX}/media/batch/delete", json={"ids": [first.id, second.id, "media_gone"]})

    assert response.status_code == 200
    assert response.json() == {"deleted": 2}
    assert [record.id for record in await library.records()] == [kept.id]
    for gone in (first, second):
        assert not await library.storage.exists(gone.storage_key)
    assert await library.storage.exists(kept.storage_key)


async def test_batch_tags_replaces_the_tags_of_every_listed_item(library: MediaLibraryEnv, client: AsyncClient) -> None:
    tagged = await library.store(_VIDEO, content_type=_MP4)
    other_tagged = await library.store(_VIDEO, content_type=_MP4)
    untouched = await library.store(_VIDEO, content_type=_MP4)

    response = await client.put(
        f"{API_PREFIX}/media/batch/tags", json={"ids": [tagged.id, other_tagged.id], "tags": ["poster", "q4"]}
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 2}
    tags_by_id = {record.id: record.tags for record in await library.records()}
    assert tags_by_id[tagged.id] == ["poster", "q4"]
    assert tags_by_id[other_tagged.id] == ["poster", "q4"]
    assert tags_by_id[untouched.id] == []
