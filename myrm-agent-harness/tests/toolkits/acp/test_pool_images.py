"""RuntimePool image passthrough: only a backend that declares it takes images gets them."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.acp.runtime.pool import RuntimePool
from myrm_agent_harness.toolkits.acp.types import (
    IMAGES_NOT_SENT_STATUS,
    BackendCapabilities,
    McpServerConfig,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)


def _pool_with_backend(
    supports_images: bool, captured: list[list[str] | None], *, event_bus: MagicMock | None = None
) -> RuntimePool:
    pool = RuntimePool(max_concurrent=1, event_bus=event_bus)
    pool.register("claude", RuntimeConfig(backend_type="cli", command="claude"))
    backend = MagicMock()
    backend.capabilities = BackendCapabilities(supports_images=supports_images)

    async def fake_run_turn(
        prompt: str,
        session_id: str,
        *,
        mcp_servers: list[McpServerConfig] | None = None,
        images: list[str] | None = None,
    ):
        captured.append(images)
        yield create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")

    backend.run_turn = fake_run_turn
    pool.get = MagicMock(return_value=backend)
    return pool


async def _events(pool: RuntimePool, *, images: list[str] | None) -> list[RuntimeEvent]:
    return [event async for event in pool.run_turn("claude", "look", session_id="s1", images=images)]


@pytest.mark.asyncio
async def test_a_backend_that_takes_images_gets_the_files_of_the_turn() -> None:
    captured: list[list[str] | None] = []
    pool = _pool_with_backend(True, captured)

    events = await _events(pool, images=["/img/a.png", "/img/b.png"])

    assert captured == [["/img/a.png", "/img/b.png"]]
    assert [event.type for event in events] == [RuntimeEventType.DONE]


@pytest.mark.asyncio
async def test_a_backend_that_does_not_take_images_is_told_nothing_and_the_turn_opens_with_a_notice(
    caplog: pytest.LogCaptureFixture,
) -> None:
    captured: list[list[str] | None] = []
    pool = _pool_with_backend(False, captured)

    with caplog.at_level("INFO", logger="myrm_agent_harness.toolkits.acp.runtime.pool"):
        events = await _events(pool, images=["/img/a.png", "/img/b.png"])

    assert captured == [None]
    assert [event.type for event in events] == [RuntimeEventType.STATUS_UPDATE, RuntimeEventType.DONE]
    assert events[0].data == {"status": IMAGES_NOT_SENT_STATUS, "images": 2}
    assert events[0].session_id == "s1"
    assert any("pool_images_skipped" in r.message and "images=2" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_a_turn_without_images_passes_none_and_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    captured: list[list[str] | None] = []
    pool = _pool_with_backend(True, captured)

    with caplog.at_level("INFO", logger="myrm_agent_harness.toolkits.acp.runtime.pool"):
        without = await _events(pool, images=None)
        empty = await _events(pool, images=[])

    assert captured == [None, None]
    assert [event.type for event in without + empty] == [RuntimeEventType.DONE, RuntimeEventType.DONE]
    assert not any("pool_images_skipped" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_the_notice_reaches_the_event_bus_before_the_events_of_the_turn() -> None:
    bus = MagicMock()
    bus.emit = AsyncMock()
    pool = _pool_with_backend(False, [], event_bus=bus)

    events = await _events(pool, images=["/img/a.png"])

    assert [call.args[0] for call in bus.emit.await_args_list] == events
    assert events[0].data.get("status") == IMAGES_NOT_SENT_STATUS
