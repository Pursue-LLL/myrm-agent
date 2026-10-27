"""Staging the images of a delegated turn: which sources are staged, what is refused, and that nothing is left behind."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import pytest

from app.services.external_agents.delegation import images
from app.services.external_agents.delegation.images import MAX_IMAGE_BYTES, stage_images

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 32


def _png_block(url: str, **extra: object) -> dict[str, object]:
    return {"type": "image_url", "image_url": {"url": url}, **extra}


def _local_path(block: object) -> Path:
    assert isinstance(block, dict)
    return Path(url2pathname(urlparse(block["image_url"]["url"]).path))


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    return tmp_path / "staging"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "screenshot.png"
    path.write_bytes(PNG)
    return path


async def test_a_local_file_is_staged_for_the_turn_and_removed_after_it(directory: Path, source: Path) -> None:
    query = [{"type": "text", "text": "what is this"}, _png_block(source.as_uri())]

    async with stage_images(query, directory=directory) as staged:
        (path,) = (Path(p) for p in staged.paths)
        assert path.parent == directory
        assert path.suffix == ".png"
        assert path.read_bytes() == PNG
        assert _local_path(staged.query[1]) == path
        assert staged.query[0] == query[0]

    assert not path.exists()
    assert source.exists()


async def test_the_staged_file_is_private_to_the_user(directory: Path, source: Path) -> None:
    async with stage_images([_png_block(source.as_uri())], directory=directory) as staged:
        assert stat.S_IMODE(os.stat(staged.paths[0]).st_mode) == 0o600
        assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700


@pytest.mark.parametrize(
    ("data", "extension"), [(PNG, "png"), (JPEG, "jpg"), (GIF, "gif"), (WEBP, "webp")], ids=["png", "jpeg", "gif", "webp"]
)
async def test_the_extension_comes_from_the_bytes_not_from_the_name(
    directory: Path, tmp_path: Path, data: bytes, extension: str
) -> None:
    misnamed = tmp_path / "photo.dat"
    misnamed.write_bytes(data)

    async with stage_images([_png_block(misnamed.as_uri())], directory=directory) as staged:
        assert Path(staged.paths[0]).suffix == f".{extension}"


async def test_an_inline_data_url_is_staged(directory: Path) -> None:
    url = "data:image/png;base64," + base64.b64encode(PNG).decode()

    async with stage_images([_png_block(url)], directory=directory) as staged:
        assert Path(staged.paths[0]).read_bytes() == PNG
        assert _local_path(staged.query[0]) == Path(staged.paths[0])


async def test_a_file_of_the_servers_own_storage_is_staged(directory: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def read(url: str) -> tuple[bytes, str]:
        assert url == "http://localhost:8000/files/storage/files/f1/content"
        return JPEG, "image/jpeg"

    monkeypatch.setattr(images, "read_image_bytes", read)

    async with stage_images([_png_block("http://localhost:8000/files/storage/files/f1/content")], directory=directory) as staged:
        assert Path(staged.paths[0]).suffix == ".jpg"
        assert Path(staged.paths[0]).read_bytes() == JPEG


async def test_an_external_address_is_never_fetched(directory: Path, caplog: pytest.LogCaptureFixture) -> None:
    block = _png_block("https://example.com/cat.png")

    with caplog.at_level(logging.WARNING, logger=images.logger.name):
        async with stage_images([block], directory=directory) as staged:
            assert staged.paths == []
            assert staged.query == [block]

    assert "reason=not_in_storage" in caplog.text
    assert "example.com" not in caplog.text


@pytest.mark.parametrize(
    ("make_block", "reason"),
    [
        (lambda tmp: _png_block((tmp / "missing.png").as_uri()), "a file that is gone"),
        (lambda tmp: _png_block("data:image/png;base64,@@@not-base64@@@"), "an undecodable data url"),
        (lambda tmp: _png_block("data:image/png,rawbytes"), "a data url that is not base64"),
        (lambda tmp: _png_block("data:image/png;base64," + "A" * (MAX_IMAGE_BYTES * 2)), "an oversized data url"),
    ],
    ids=["missing-file", "bad-base64", "not-base64", "oversized-data-url"],
)
async def test_an_image_that_cannot_be_staged_stays_as_it_was(
    directory: Path, tmp_path: Path, make_block: Callable[[Path], dict[str, object]], reason: str
) -> None:
    block = make_block(tmp_path)

    async with stage_images([block], directory=directory) as staged:
        assert staged.paths == [], reason
        assert staged.query == [block]


async def test_bytes_that_are_not_an_image_are_refused_whatever_the_name(directory: Path, tmp_path: Path) -> None:
    disguised = tmp_path / "notes.png"
    disguised.write_text("api_key=sk-secret")

    async with stage_images([_png_block(disguised.as_uri())], directory=directory) as staged:
        assert staged.paths == []
    assert not list(directory.iterdir())


@pytest.mark.parametrize(
    "data",
    [
        b"BM" + b"\x00" * 32,
        b"BM25 results are in",
        b"RIFF\x00\x00\x00\x00WAVE" + b"\x00" * 32,
        b"\xff\xd8\xff",
        b"GIF90a" + b"\x00" * 32,
    ],
    ids=["bmp", "text-that-starts-with-bm", "wav", "three-byte-jpeg-signature", "unknown-gif-version"],
)
async def test_a_format_no_model_takes_is_refused_even_when_it_looks_like_a_file_type_we_know(
    directory: Path, tmp_path: Path, data: bytes
) -> None:
    path = tmp_path / "picture.png"
    path.write_bytes(data)

    async with stage_images([_png_block(path.as_uri())], directory=directory) as staged:
        assert staged.paths == []
    assert not list(directory.iterdir())


async def test_the_size_limit_is_inclusive(directory: Path, tmp_path: Path) -> None:
    at_limit = tmp_path / "at_limit.png"
    at_limit.write_bytes(PNG + b"\x00" * (MAX_IMAGE_BYTES - len(PNG)))
    over = tmp_path / "over.png"
    over.write_bytes(PNG + b"\x00" * (MAX_IMAGE_BYTES - len(PNG) + 1))

    async with stage_images([_png_block(at_limit.as_uri()), _png_block(over.as_uri())], directory=directory) as staged:
        assert len(staged.paths) == 1
        assert staged.query[1] == _png_block(over.as_uri())


async def test_a_video_is_not_staged(directory: Path, tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(PNG)
    block = _png_block(video.as_uri(), _mime_type="video/mp4")

    async with stage_images([block], directory=directory) as staged:
        assert staged.paths == []
        assert staged.query == [block]
    assert not directory.exists()


async def test_one_bad_image_does_not_stop_the_others(directory: Path, source: Path, tmp_path: Path) -> None:
    bad = _png_block((tmp_path / "missing.png").as_uri())
    good = _png_block(source.as_uri())

    async with stage_images([bad, good], directory=directory) as staged:
        assert len(staged.paths) == 1
        assert staged.query[0] == bad
        assert _local_path(staged.query[1]) == Path(staged.paths[0])


@pytest.mark.parametrize(
    "query", ["just text", [{"type": "text", "text": "hi"}], [], None], ids=["str", "text-only", "empty", "none"]
)
async def test_a_turn_without_images_touches_nothing_on_disk(directory: Path, query: object) -> None:
    async with stage_images(query, directory=directory) as staged:
        assert staged.query is query
        assert staged.paths == []
    assert not directory.exists()


async def test_the_files_are_removed_when_the_turn_fails(directory: Path, source: Path) -> None:
    with pytest.raises(RuntimeError, match="turn failed"):
        async with stage_images([_png_block(source.as_uri())], directory=directory) as staged:
            path = Path(staged.paths[0])
            assert path.exists()
            raise RuntimeError("turn failed")

    assert not path.exists()


async def test_the_files_are_removed_when_the_turn_is_cancelled(directory: Path, source: Path) -> None:
    started = asyncio.Event()
    paths: list[Path] = []

    async def turn() -> None:
        async with stage_images([_png_block(source.as_uri())], directory=directory) as staged:
            paths.append(Path(staged.paths[0]))
            started.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(turn())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not paths[0].exists()


async def test_a_file_a_stopped_server_left_behind_is_swept_but_a_fresh_one_is_not(directory: Path, source: Path) -> None:
    directory.mkdir()
    stale = directory / "stale.png"
    stale.write_bytes(PNG)
    long_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(stale, (long_ago, long_ago))
    fresh = directory / "fresh.png"
    fresh.write_bytes(PNG)

    async with stage_images([_png_block(source.as_uri())], directory=directory):
        pass

    assert not stale.exists()
    assert fresh.exists()


async def test_the_sweep_never_follows_a_symlink(directory: Path, tmp_path: Path, source: Path) -> None:
    directory.mkdir()
    outside = tmp_path / "outside.png"
    outside.write_bytes(PNG)
    long_ago = time.time() - 2 * 24 * 60 * 60
    os.utime(outside, (long_ago, long_ago))
    link = directory / "link.png"
    link.symlink_to(outside)

    async with stage_images([_png_block(source.as_uri())], directory=directory):
        pass

    assert outside.exists()
    assert link.is_symlink()


async def test_an_unusable_directory_leaves_the_turn_as_it_was(tmp_path: Path, source: Path) -> None:
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("a file where the directory should be")
    block = _png_block(source.as_uri())

    async with stage_images([block], directory=blocked) as staged:
        assert staged.paths == []
        assert staged.query == [block]


def test_the_directory_is_fixed_under_the_state_dir() -> None:
    from app.config.settings import settings

    assert images.staging_dir() == Path(settings.database.state_dir) / "delegation-images"
    assert images.staging_dir() == images.staging_dir()
