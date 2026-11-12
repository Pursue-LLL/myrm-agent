"""Unit tests for stream_silence: the silence the live tests lean on has to be measured from the log, never assumed."""

from __future__ import annotations

import pytest

from tests.support.stream_silence import (
    Chunk,
    Request,
    Silence,
    StreamLog,
    ended_at,
    last_heard,
    loading_falls,
    longest_silence,
    parse_stream_log,
)


def _log(*chunks: tuple[int, str, int], loading: tuple[tuple[int, bool], ...] = ()) -> StreamLog:
    return StreamLog(chunks=tuple(Chunk(*chunk) for chunk in chunks), requests=(), loading=loading, watchdog=())


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


def test_the_moment_a_stream_is_stalled_neither_ends_nor_starts_a_silence() -> None:
    log = _log((0, "data", 1), (40_000, "stalled", 1), (45_000, "data", 2), (66_000, "data", 2))

    assert longest_silence(log) == Silence(start_ms=45_000, end_ms=66_000, heartbeats=())


def test_a_silence_is_never_measured_across_two_streams() -> None:
    log = _log((0, "data", 1), (100_000, "data", 2))

    assert longest_silence(log) is None


def test_an_empty_log_holds_no_silence() -> None:
    assert longest_silence(_log()) is None


def test_a_stream_was_last_heard_at_its_last_data_or_keep_alive_frame() -> None:
    log = _log((0, "data", 1), (3_000, "data", 1), (18_000, "heartbeat", 1), (4_000, "stalled", 1), (20_000, "data", 2))

    assert last_heard(log, 1) == 18_000
    assert last_heard(log, 2) == 20_000


def test_the_end_of_a_stream_and_the_moment_it_stalled_are_not_hearing_from_it() -> None:
    log = _log((0, "data", 1), (50_000, "stalled", 1), (60_000, "eof", 1))

    assert last_heard(log, 1) == 0


def test_a_stream_that_was_never_heard_has_no_last_heard() -> None:
    with pytest.raises(AssertionError, match="received nothing on stream 3"):
        last_heard(_log((0, "data", 1)), 3)


def test_a_stream_ends_when_the_server_closes_it() -> None:
    log = _log((0, "data", 1), (5_000, "eof", 1), (6_000, "data", 2), (9_000, "eof", 2))

    assert ended_at(log, 1) == 5_000
    assert ended_at(log, 2) == 9_000


def test_a_stream_that_stalled_or_was_never_seen_has_no_end() -> None:
    log = _log((0, "data", 1), (4_000, "stalled", 1), (90_000, "eof", 2))

    assert ended_at(log, 1) is None
    assert ended_at(log, 3) is None


def test_a_stream_the_page_cancelled_has_no_end() -> None:
    log = _log((0, "data", 1), (45_000, "cancelled", 1))

    assert ended_at(log, 1) is None


def test_the_page_cancelling_a_stream_does_not_end_a_silence() -> None:
    log = _log((0, "data", 1), (45_000, "cancelled", 1))

    assert longest_silence(log) is None


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
        "requests": [[0, "run", 1], [150, "attach", 2]],
        "loading": [[0, False], [50, True]],
        "watchdog": ["[StreamWatchdog] Missing terminal event detected (usage received without terminal event after 1500ms)."],
    }

    log = parse_stream_log(state)

    assert log.chunks == (Chunk(100, "data", 1), Chunk(200, "eof", 1))
    assert log.requests == (Request(0, "run", 1), Request(150, "attach", 2))
    assert log.loading == ((0, False), (50, True))
    assert log.watchdog == (
        "[StreamWatchdog] Missing terminal event detected (usage received without terminal event after 1500ms).",
    )


@pytest.mark.parametrize(
    "state",
    [
        {"chunks": [], "requests": [], "loading": []},
        {"chunks": "none", "requests": [], "loading": [], "watchdog": []},
        {"chunks": [[1.5, "data", 1]], "requests": [], "loading": [], "watchdog": []},
        {"chunks": [], "requests": [], "loading": [[True, True]], "watchdog": []},
        {"chunks": [], "requests": [], "loading": [], "watchdog": [3]},
        {"chunks": [5], "requests": [], "loading": [], "watchdog": []},
        {"chunks": [], "loading": [], "watchdog": []},
        {"chunks": [], "requests": "none", "loading": [], "watchdog": []},
        {"chunks": [], "requests": [[2.5, "attach", 1]], "loading": [], "watchdog": []},
        {"chunks": [], "requests": [3], "loading": [], "watchdog": []},
    ],
)
def test_a_malformed_page_log_fails_instead_of_passing(state: dict[str, object]) -> None:
    with pytest.raises(AssertionError):
        parse_stream_log(state)
