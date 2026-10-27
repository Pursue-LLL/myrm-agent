"""A delegated run that stays quiet for minutes tells its chat it is still working, and stops when the run does.

The run's own progress is not shown in the chat, so the heartbeat is the only sign of life. It edits one message in
place, counts the run's steps, and ends with the run, whether the run finished, was stopped or stopped at an approval.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.delegation import DelegationCoordinator, DelegationTask, build_delegation_task, delegation_heartbeat
from app.channels.types import ChannelCapabilities, InboundMessage, OutboundMessage, ProgressUpdate, QuickReply, StreamingText

_TICK = 0.05
_APPROVAL = ProgressUpdate(
    label="shell needs approval", quick_replies=(QuickReply(label="Approve", text="/approve", required=True),)
)

Stream = Callable[[], AsyncGenerator[object, None]]


class _Channel:
    capabilities = ChannelCapabilities(edit=True)


def _bus() -> MagicMock:
    bus = MagicMock()
    bus.get_channel = MagicMock(return_value=_Channel())
    bus.send_tracked = AsyncMock(return_value="beat-1")
    bus.edit_channel_message = AsyncMock(return_value=True)
    bus.publish_outbound = AsyncMock()
    return bus


def _beats(bus: MagicMock) -> int:
    return bus.send_tracked.call_count + bus.edit_channel_message.call_count


def _inbound() -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id="u1", chat_id="c1", content="x", user_id="u1", metadata={"locale": "en"})


class _Executor:
    def __init__(self, stream: Stream) -> None:
        self._stream = stream

    def execute_stream(self, *_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
        return self._stream()


def _task(coordinator: DelegationCoordinator, timeout_seconds: float = 3600.0) -> DelegationTask:
    task = build_delegation_task(
        origin_channel="telegram", origin_user_id="u1", origin_chat_id="c1", prompt="do it", timeout_seconds=timeout_seconds
    )
    coordinator.register_task(task)
    return task


async def _no_hand_over(_request: ProgressUpdate) -> None:
    return None


async def _run(
    stream: Stream, bus: MagicMock, *, timeout_seconds: float = 3600.0, hand_over: Callable[..., object] = _no_hand_over
) -> None:
    coordinator = DelegationCoordinator()
    task = _task(coordinator, timeout_seconds)
    await coordinator.execute_task_lifecycle(
        task,
        _Executor(stream),
        bus,
        _inbound(),
        hand_over_approval=hand_over,  # type: ignore[arg-type]
    )


async def _until_beat(bus: MagicMock) -> None:
    for _ in range(100):
        if _beats(bus):
            return
        await asyncio.sleep(_TICK / 5)
    raise AssertionError("no heartbeat was sent")


@pytest.fixture(autouse=True)
def _fast_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(delegation_heartbeat, "HEARTBEAT_INTERVAL_SECONDS", _TICK)


def _slow(seconds: float, *events: object) -> Stream:
    async def stream() -> AsyncGenerator[object, None]:
        for event in events:
            yield event
        await asyncio.sleep(seconds)
        yield OutboundMessage(channel="telegram", recipient_id="c1", content="done", user_id="u1")

    return stream


@pytest.mark.asyncio
async def test_a_long_run_edits_one_heartbeat_in_place_with_its_task_and_steps() -> None:
    bus = _bus()
    progress = ProgressUpdate(label="searching the web")

    await _run(_slow(_TICK * 4.5, StreamingText(text="working"), progress, progress), bus)

    bus.send_tracked.assert_called_once()
    first: OutboundMessage = bus.send_tracked.call_args.args[0]
    assert first.recipient_id == "c1"
    assert "Background task" in first.content and "2 steps" in first.content
    assert bus.edit_channel_message.call_count >= 1
    assert bus.edit_channel_message.call_args.args[:3] == ("telegram", "c1", "beat-1")


@pytest.mark.asyncio
async def test_a_run_shorter_than_one_interval_sends_no_heartbeat() -> None:
    bus = _bus()

    await _run(_slow(_TICK / 5), bus)

    assert _beats(bus) == 0


@pytest.mark.asyncio
async def test_the_heartbeats_stop_at_the_tasks_time_limit() -> None:
    bus = _bus()

    await _run(_slow(_TICK * 6), bus, timeout_seconds=_TICK * 2.5)

    assert _beats(bus) == 2


@pytest.mark.asyncio
async def test_the_heartbeat_ends_with_the_run() -> None:
    bus = _bus()
    before = asyncio.all_tasks()

    await _run(_slow(_TICK * 2.5), bus)
    sent = _beats(bus)
    await asyncio.sleep(_TICK * 3)

    assert sent >= 1
    assert _beats(bus) == sent
    assert asyncio.all_tasks() == before


@pytest.mark.asyncio
async def test_the_heartbeat_ends_when_the_user_stops_the_run() -> None:
    bus = _bus()
    runner = asyncio.create_task(_run(_slow(_TICK * 100), bus))
    await _until_beat(bus)

    runner.cancel()
    with pytest.raises(asyncio.CancelledError):
        await runner
    sent = _beats(bus)
    await asyncio.sleep(_TICK * 3)

    assert _beats(bus) == sent


@pytest.mark.asyncio
async def test_the_heartbeat_is_over_before_the_approval_is_handed_to_the_chat() -> None:
    bus = _bus()
    beats_while_waiting: list[int] = []

    async def hand_over(_request: ProgressUpdate) -> None:
        before = _beats(bus)
        await asyncio.sleep(_TICK * 3)
        beats_while_waiting.append(_beats(bus) - before)

    await _run(_slow(_TICK * 2.5, _APPROVAL), bus, hand_over=hand_over)

    assert beats_while_waiting == [0]
