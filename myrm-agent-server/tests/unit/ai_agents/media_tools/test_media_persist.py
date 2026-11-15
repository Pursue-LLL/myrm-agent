"""The persistence callback shared by the image, video and TTS engines."""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from app.ai_agents.media_tools.media_persist import create_media_persist_callback
from app.core.media.reference import parse_media_reference
from tests.support.media_library_env import MediaLibraryEnv, media_library_env


@dataclass(frozen=True, slots=True)
class _ImageMeta:
    prompt: str | None
    model: str | None
    resolution: str | None = None


@dataclass(frozen=True, slots=True)
class _AudioMeta:
    """Audio metadata has no resolution, like the TTS engine's own ``MediaMeta``."""

    prompt: str | None
    model: str | None


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, "PNG")
    return buffer.getvalue()


@pytest.fixture
async def library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[MediaLibraryEnv]:
    async with media_library_env(tmp_path / "storage", monkeypatch) as env:
        yield env


async def test_a_stored_image_is_returned_as_its_reference_and_keeps_its_metadata(library: MediaLibraryEnv) -> None:
    image = _png()
    persist = create_media_persist_callback(chat_id="chat-1", model_name="engine-model", source="image_tool")

    reference = await persist(
        image, "image/png", _ImageMeta(prompt="a lighthouse", model="gpt-image-2.6-sunburst", resolution="16x16")
    )

    (record,) = await library.records()
    assert reference == f"media://{record.id}"
    assert parse_media_reference(reference) == record.id
    assert (
        record.media_type,
        record.source,
        record.prompt,
        record.model,
        record.resolution,
        record.session_id,
        record.content_type,
        record.file_size,
    ) == ("image", "image_tool", "a lighthouse", "gpt-image-2.6-sunburst", "16x16", "chat-1", "image/png", len(image))
    assert await library.storage.read(record.storage_key) == image
    assert record.thumbnail_key is not None
    assert await library.storage.read(record.thumbnail_key)


@pytest.mark.parametrize("chat_id", [None, "", "   "])
async def test_a_background_job_without_a_chat_is_stored_all_the_same(library: MediaLibraryEnv, chat_id: str | None) -> None:
    persist = create_media_persist_callback(chat_id=chat_id, model_name="engine-model", source="video_tool")

    reference = await persist(b"\x00\x00\x00\x18ftypmp42", "video/mp4", _ImageMeta(prompt="a drone shot", model=None))

    (record,) = await library.records()
    assert reference == f"media://{record.id}"
    assert (record.media_type, record.session_id) == ("video", None)


async def test_a_blank_chat_id_is_trimmed_before_it_links_the_conversation(library: MediaLibraryEnv) -> None:
    persist = create_media_persist_callback(chat_id="  chat-7  ", model_name=None, source="image_tool")

    await persist(_png(), "image/png", _ImageMeta(prompt=None, model=None))

    (record,) = await library.records()
    assert record.session_id == "chat-7"


async def test_the_engines_model_wins_and_the_callbacks_model_is_only_the_fallback(library: MediaLibraryEnv) -> None:
    persist = create_media_persist_callback(chat_id=None, model_name="configured-model", source="image_tool")

    await persist(_png(), "image/png", _ImageMeta(prompt=None, model="fallback-used"))
    await persist(_png(), "image/png", _ImageMeta(prompt=None, model=None))

    models = sorted(record.model or "" for record in await library.records())
    assert models == ["configured-model", "fallback-used"]


async def test_audio_is_stored_without_a_resolution(library: MediaLibraryEnv) -> None:
    persist = create_media_persist_callback(chat_id="chat-1", model_name="tts-model", source="tts_generate")

    reference = await persist(b"ID3audio", "audio/mpeg", _AudioMeta(prompt="hello", model=None))

    (record,) = await library.records()
    assert reference == f"media://{record.id}"
    assert (record.media_type, record.resolution, record.model, record.thumbnail_key) == ("audio", None, "tts-model", None)


async def test_a_storage_failure_raises_and_leaves_no_record(library: MediaLibraryEnv, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(library.storage, "write", AsyncMock(side_effect=OSError("disk full")))
    persist = create_media_persist_callback(chat_id="chat-1", model_name="engine-model", source="image_tool")

    with pytest.raises(OSError, match="disk full"):
        await persist(_png(), "image/png", _ImageMeta(prompt="a lighthouse", model=None))

    assert await library.records() == []
