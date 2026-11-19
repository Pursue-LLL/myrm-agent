"""The media cards seed route leaves a chat the way a finished generation turn does, with real stored files.

[INPUT]
- app.api.chats.test_fixtures.media_cards (POS: the seed route under test)
- tests.support.media_library_env::media_library_env (POS: the media library on a throwaway database and storage)
- myrm_agent_harness.toolkits.tasks::SQLiteTaskStore (POS: the real task store the cards read their task from)

[OUTPUT]
Fails when a kind stores a file its card cannot play, registers an entry other than the one a media tool result
registers, loses the task a task card follows, or when the negative controls stop being unloadable or expired.

[POS]
Guards the fixture the real-browser media cards test (tests/e2e/test_media_cards_chrome_e2e.py) seeds its chats with.
"""

from __future__ import annotations

import io
import wave
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStatus
from PIL import Image

from tests.support.media_library_env import MediaLibraryEnv, media_library_env
from tests.support.minimal_app import build_minimal_app

_SEED_URL = "/api/v1/chats/test/seed-media-cards-fixture"
_FIXTURE_MODULE = "app.api.chats.test_fixtures.media_cards"
_EBML_MAGIC = b"\x1a\x45\xdf\xa3"
_UNREACHABLE_MARKER = "myrm-e2e-media-unreachable"


class _Seeding:
    """The seam of one test: the library and task store the route writes to, and the messages it appended."""

    def __init__(self, library: MediaLibraryEnv, store: SQLiteTaskStore, client: AsyncClient, messages: AsyncMock) -> None:
        self.library = library
        self.store = store
        self.client = client
        self.messages = messages

    async def seed(self, kind: str, address: str | None = None) -> httpx.Response:
        params = {"kind": kind, **({"address": address} if address else {})}
        return await self.client.post(_SEED_URL, params=params)


@pytest.fixture
async def seeding(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Seeding]:
    store = SQLiteTaskStore(db_path=str(tmp_path / "tasks.db"))
    await store.initialize()
    messages = AsyncMock()
    async with media_library_env(tmp_path / "storage", monkeypatch) as library:
        with (
            patch(f"{_FIXTURE_MODULE}.is_local_mode", return_value=True),
            patch(f"{_FIXTURE_MODULE}.get_task_store", return_value=store),
            patch(f"{_FIXTURE_MODULE}.AgentService.get_agent_list", new=AsyncMock(return_value=([], 0))),
            patch(f"{_FIXTURE_MODULE}.ChatService.create_or_update_chat", new=AsyncMock()),
            patch(f"{_FIXTURE_MODULE}.ChatService.append_message", new=messages),
        ):
            transport = ASGITransport(app=build_minimal_app(preset="chats"))
            async with AsyncClient(transport=transport, base_url="http://testserver") as client:
                yield _Seeding(library, store, client, messages)


async def _stored_bytes(library: MediaLibraryEnv, media_id: str) -> bytes:
    (record,) = [r for r in await library.records() if r.id == media_id]
    return await library.storage.read(record.storage_key)


@pytest.mark.parametrize(
    ("kind", "content_type", "entry_kind", "task_type"),
    [
        ("image", "image/png", "image", "image_generate"),
        ("video", "video/webm", "video", "video_generate"),
        ("image_edit", "image/png", "image", None),
        ("tts", "audio/wav", "tts", None),
    ],
)
async def test_each_kind_stores_a_real_file_and_registers_its_entry(
    seeding: _Seeding, kind: str, content_type: str, entry_kind: str, task_type: str | None
) -> None:
    response = await seeding.seed(kind)

    assert response.status_code == 200, response.text
    body = response.json()
    entry = body["entry"]
    marker = body["marker"]
    assert entry["kind"] == entry_kind
    assert body["ui_path"] == f"/{body['chat_id']}"

    (record,) = await seeding.library.records()
    assert (record.id, record.content_type) == (marker, content_type)
    reference = f"media://{marker}"

    if task_type is None:
        assert entry["media"] == reference
        assert "task_id" not in entry
    else:
        task = await seeding.store.get_task(entry["task_id"])
        assert task is not None
        assert (task.status, task.task_type) == (TaskStatus.SUCCEEDED, task_type)
        assert task.payload["chat_id"] == body["chat_id"]
        result = task.result or {}
        assert (result["images"][0]["url"] if kind == "image" else result["video_urls"][0]) == reference

    # The assistant reply carries words next to the registered entry, which is all the card needs.
    user_call, assistant_call = seeding.messages.await_args_list
    assert user_call.args[:2] == (body["chat_id"], "user")
    assert assistant_call.args[:3] == (body["chat_id"], "assistant", "MYRM_E2E_MEDIA_CARD_REPLY")
    assert assistant_call.kwargs["extra_data"] == {"media_generated": [entry]}


async def test_the_stored_files_are_ones_the_cards_can_play(seeding: _Seeding) -> None:
    image = (await seeding.seed("image")).json()["marker"]
    clip = (await seeding.seed("video")).json()["marker"]
    speech = (await seeding.seed("tts")).json()["marker"]

    assert Image.open(io.BytesIO(await _stored_bytes(seeding.library, image))).size == (64, 64)
    assert (await _stored_bytes(seeding.library, clip)).startswith(_EBML_MAGIC)
    with wave.open(io.BytesIO(await _stored_bytes(seeding.library, speech))) as wav:
        assert wav.getnframes() == wav.getframerate()


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_an_unreachable_address_is_a_task_result_no_browser_can_load(seeding: _Seeding, kind: str) -> None:
    body = (await seeding.seed(kind, "file")).json()

    assert body["marker"] == _UNREACHABLE_MARKER
    task = await seeding.store.get_task(body["entry"]["task_id"])
    assert task is not None
    result = task.result or {}
    address = result["images"][0]["url"] if kind == "image" else result["video_urls"][0]
    assert address.startswith("file://")
    assert address.endswith(_UNREACHABLE_MARKER)
    assert await seeding.library.records() == []


@pytest.mark.parametrize("kind", ["image", "video"])
async def test_an_expired_card_has_no_task_record_and_no_file(seeding: _Seeding, kind: str) -> None:
    body = (await seeding.seed(kind, "expired")).json()

    assert body["marker"] is None
    assert await seeding.store.get_task(body["entry"]["task_id"]) is None
    assert await seeding.library.records() == []


@pytest.mark.parametrize("kind", ["image_edit", "tts"])
@pytest.mark.parametrize("address", ["file", "expired"])
async def test_only_a_task_card_can_point_at_an_unreachable_or_expired_result(seeding: _Seeding, kind: str, address: str) -> None:
    response = await seeding.seed(kind, address)

    assert response.status_code == 400
    assert await seeding.library.records() == []


async def test_the_route_is_local_mode_only(seeding: _Seeding) -> None:
    with patch(f"{_FIXTURE_MODULE}.is_local_mode", return_value=False):
        response = await seeding.seed("image")

    assert response.status_code == 404
    assert await seeding.library.records() == []


async def test_a_chat_is_bound_to_the_first_agent_when_there_is_one(seeding: _Seeding) -> None:
    agent = MagicMock()
    agent.id = "agent-e2e-media"
    create_chat = AsyncMock()
    with (
        patch(f"{_FIXTURE_MODULE}.AgentService.get_agent_list", new=AsyncMock(return_value=([agent], 1))),
        patch(f"{_FIXTURE_MODULE}.ChatService.create_or_update_chat", new=create_chat),
    ):
        response = await seeding.seed("image")

    assert response.status_code == 200
    assert create_chat.await_args.args[0].agent_id == "agent-e2e-media"
