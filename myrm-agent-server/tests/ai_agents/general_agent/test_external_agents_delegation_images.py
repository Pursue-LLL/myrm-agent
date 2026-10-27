"""A direct delegation turn with attached images: staged for the CLI for the length of the turn, removed after it."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.acp.types import RuntimeEventType
from myrm_agent_harness.utils import CancellationToken

from app.ai_agents.general_agent.external_agents import ExternalAgentsMixin
from app.services.external_agents.delegation import images

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class _RecordingPool:
    """A pool whose turn records what the CLI would be given and whether the images were still there."""

    def __init__(self, *, endless: bool = False) -> None:
        self.prompts: list[str] = []
        self.images: list[list[str] | None] = []
        self.present_during_turn: list[bool] = []
        self.turn_closed = asyncio.Event()
        self._endless = endless

    def get_config(self, name: str) -> SimpleNamespace:
        return SimpleNamespace(auth_mode="api_key", command="claude")

    async def cancel(self, name: str, session_id: str) -> None:
        return None

    async def run_turn(self, name: str, prompt: str, session_id: str, *, images: list[str] | None = None, **_: object):
        self.prompts.append(prompt)
        self.images.append(images)
        self.present_during_turn.append(all(Path(path).exists() for path in images or []))
        try:
            yield SimpleNamespace(type=RuntimeEventType.TEXT_DELTA, data={"content": "seen"})
            while self._endless:
                await asyncio.sleep(0)
                yield SimpleNamespace(type=RuntimeEventType.TEXT_DELTA, data={"content": "more"})
        finally:
            self.turn_closed.set()


@pytest.fixture
def staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "state" / "delegation-images"
    monkeypatch.setattr(images, "staging_dir", lambda: directory)
    return directory


def _mixin(pool: object) -> ExternalAgentsMixin:
    mixin = ExternalAgentsMixin.__new__(ExternalAgentsMixin)
    mixin._runtime_pool = pool
    mixin.locale = "en"
    mixin.quote = None
    return mixin


def _query(tmp_path: Path) -> list[dict[str, object]]:
    screenshot = tmp_path / "shot.png"
    screenshot.write_bytes(PNG)
    return [
        {"type": "text", "text": "what is wrong here"},
        {"type": "image_url", "image_url": {"url": screenshot.as_uri()}},
    ]


async def _cancel_on_first_message(stream: AsyncGenerator[dict[str, object]], token: CancellationToken):
    """Pass the stream's events through, tripping ``token`` the moment the CLI's first text arrives."""
    async for event in stream:
        yield event
        if event["type"] == AgentEventType.MESSAGE.value:
            token.cancel()


def _leftovers(directory: Path) -> list[Path]:
    return list(directory.iterdir()) if directory.exists() else []


async def test_the_cli_gets_the_staged_files_and_a_prompt_that_points_at_them(tmp_path: Path, staging: Path) -> None:
    pool = _RecordingPool()

    events = [event async for event in _mixin(pool)._direct_delegate_stream("claude", _query(tmp_path), chat_id="c1")]

    ((staged,),) = pool.images
    assert Path(staged).parent == staging
    assert pool.present_during_turn == [True]
    assert pool.prompts == [f"what is wrong here\n\n[Image: {staged}]"]
    assert any(event["type"] == AgentEventType.MESSAGE.value for event in events)


async def test_the_staged_files_are_gone_once_the_turn_is_over(tmp_path: Path, staging: Path) -> None:
    pool = _RecordingPool()

    async for _ in _mixin(pool)._direct_delegate_stream("claude", _query(tmp_path), chat_id="c1"):
        pass

    assert _leftovers(staging) == []


async def test_closing_the_stream_early_stops_the_turn_and_removes_the_files(tmp_path: Path, staging: Path) -> None:
    pool = _RecordingPool(endless=True)
    stream = _mixin(pool)._direct_delegate_stream("claude", _query(tmp_path), chat_id="c1")

    async for event in stream:
        if event["type"] == AgentEventType.MESSAGE.value:
            break
    assert len(_leftovers(staging)) == 1
    await stream.aclose()

    assert pool.turn_closed.is_set()
    assert _leftovers(staging) == []


async def test_a_text_turn_stages_nothing_and_hands_the_pool_no_images(staging: Path) -> None:
    pool = _RecordingPool()

    async for _ in _mixin(pool)._direct_delegate_stream("claude", "just text", chat_id="c1"):
        pass

    assert pool.images == [None]
    assert pool.prompts == ["just text"]
    assert not staging.exists()


async def test_an_image_that_cannot_be_staged_still_runs_the_turn_with_the_path_line(tmp_path: Path, staging: Path) -> None:
    pool = _RecordingPool()
    query = [{"type": "image_url", "image_url": {"url": "https://example.com/cat.png"}}]

    async for _ in _mixin(pool)._direct_delegate_stream("claude", query, chat_id="c1"):
        pass

    assert pool.images == [None]
    assert pool.prompts == ["[Image: https://example.com/cat.png]"]


async def test_the_turn_still_cancels_through_the_pool(tmp_path: Path, staging: Path) -> None:
    pool = _RecordingPool(endless=True)
    pool.cancel = AsyncMock()
    token = CancellationToken()
    stream = _mixin(pool)._direct_delegate_stream("claude", _query(tmp_path), cancel_token=token, chat_id="c1")

    seen = [event["type"] async for event in _cancel_on_first_message(stream, token)]
    await stream.aclose()

    assert seen[-1] == AgentEventType.CANCELLED.value
    pool.cancel.assert_awaited()
    assert pool.turn_closed.is_set()
    assert _leftovers(staging) == []
