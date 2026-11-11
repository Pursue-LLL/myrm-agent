"""Unit tests for stream_silence: the silence the live tests lean on has to be measured from the log, never assumed."""

from __future__ import annotations

import asyncio

import pytest
from myrm_agent_harness.agent.streaming.stream_buffer import ResilientStreamBuffer

from tests.support.stream_silence import (
    HEARTBEAT_FRAME,
    Chunk,
    Silence,
    StreamLog,
    loading_falls,
    longest_silence,
    parse_stream_log,
)


def _log(*chunks: tuple[int, str, int], loading: tuple[tuple[int, bool], ...] = ()) -> StreamLog:
    return StreamLog(chunks=tuple(Chunk(*chunk) for chunk in chunks), loading=loading, watchdog=())


@pytest.mark.asyncio
async def test_the_frame_the_probe_swallows_is_the_frame_an_idle_server_sends() -> None:
    buffer = ResilientStreamBuffer("stream-silence-frame")

    async def feed() -> None:
        await buffer.append('data: {"type":"first"}\n\n')
        await asyncio.sleep(0.2)
        await buffer.end_stream()

    feeder = asyncio.create_task(feed())
    frames = [frame async for frame in buffer.subscribe(heartbeat_interval=0.05)]
    await feeder

    assert HEARTBEAT_FRAME in frames


def test_the_longest_silence_lists_the_keep_alive_frames_inside_it() -> None:
    log = _log(
        (100, "data", 1),
        (15_100, "heartbeat", 1),
        (30_100, "heartbeat", 1),
        (40_000, "data", 1),
        (41_000, "data", 1),
        (56_000, "heartbeat", 1),
        (57_000, "eof", 1),
    )

    assert longest_silence(log) == Silence(start_ms=100, end_ms=40_000, heartbeats=(15_100, 30_100))


def test_keep_alive_frames_are_not_data_that_ends_a_silence() -> None:
    log = _log((0, "data", 1), (15_000, "heartbeat", 1), (30_000, "heartbeat", 1), (60_000, "eof", 1))

    assert longest_silence(log) == Silence(start_ms=0, end_ms=60_000, heartbeats=(15_000, 30_000))


def test_a_silence_is_never_measured_across_two_streams() -> None:
    log = _log((0, "data", 1), (100_000, "data", 2))

    assert longest_silence(log) is None


def test_an_empty_log_holds_no_silence() -> None:
    assert longest_silence(_log()) is None


def test_the_page_falls_idle_once_the_turn_is_over() -> None:
    log = _log(loading=((0, False), (500, True), (70_000, False)))

    assert loading_falls(log) == (70_000,)


def test_every_fall_is_reported_and_the_state_before_the_turn_is_not_one() -> None:
    log = _log(loading=((0, True), (10, False), (20, True), (30, False)))

    assert loading_falls(log) == (10, 30)


def test_a_page_that_never_got_busy_has_no_fall() -> None:
    assert loading_falls(_log(loading=((0, False),))) == ()
    assert loading_falls(_log()) == ()


def test_a_well_formed_page_log_is_parsed() -> None:
    state: dict[str, object] = {
        "ready": True,
        "chunks": [[100, "data", 1], [200, "eof", 1]],
        "loading": [[0, False], [50, True]],
        "watchdog": ["[StreamWatchdog] Missing terminal event detected (silence timeout of 45000ms)."],
    }

    log = parse_stream_log(state)

    assert log.chunks == (Chunk(100, "data", 1), Chunk(200, "eof", 1))
    assert log.loading == ((0, False), (50, True))
    assert log.watchdog == ("[StreamWatchdog] Missing terminal event detected (silence timeout of 45000ms).",)


@pytest.mark.parametrize(
    "state",
    [
        {"chunks": [], "loading": []},
        {"chunks": "none", "loading": [], "watchdog": []},
        {"chunks": [[1.5, "data", 1]], "loading": [], "watchdog": []},
        {"chunks": [], "loading": [[True, True]], "watchdog": []},
        {"chunks": [], "loading": [], "watchdog": [3]},
        {"chunks": [5], "loading": [], "watchdog": []},
    ],
)
def test_a_malformed_page_log_fails_instead_of_passing(state: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        parse_stream_log(state)
