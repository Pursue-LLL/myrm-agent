"""A turn the server holds silent for a minute keeps the page busy for as long as its connection delivers, and a connection that
stops delivering altogether is replaced by the attach stream within the stream consumer's liveness budget.

A skill's PreToolUse hook sleeps before the model's bash call runs. The pre-call guards run before the tool's own heartbeat task
starts, so for that stretch the real turn sends nothing: the server answers only with its keep-alive frame every 15 s. Both tests
run that real turn against the real wire.

- The keep-alive frames reach the page: the chat stays busy (``loading``) through the whole silence on the one request the page
  sent, and the page opens no other stream while the turn is silent.
- The connection dies a few seconds after its data began to flow (the probe stops delivering anything, as a network path that
  vanished without a reset does): the page notices after three keep-alive intervals and attaches to the turn that is still
  running. It stays busy while the attach stream, which sends the same keep-alive frames, carries it through the rest of the
  silence, and it shows the reply the turn produced.

A page bound to an E2E runtime looks for a pending approval with attach requests of its own once a stream has ended; they follow
the turn's data, so the tests judge the requests the page opened while the turn was still going.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

import pytest

from tests.support.chrome_chat_page_observe import wait_for_reply_on_page
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_ui_url
from tests.support.chrome_skill_hooks_composer import drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, setup_skill_chat
from tests.support.e2e_runtime_guard import E2EResourceLedger
from tests.support.stream_silence import (
    STREAM_END_TIMEOUT_SEC,
    Silence,
    StreamLog,
    ended_at,
    install_stream_probe,
    last_heard,
    loading_falls,
    longest_silence,
    wait_for_stream_log,
)

_HOLD_SEC = 70
# The attach stream opens one liveness budget after the connection died; the silence it carries until the hold ends must still
# fit the minimum below with room to spare.
_STALL_HOLD_SEC = 110
# The hold minus the model's own pauses on either side of it; three keep-alive intervals fit in it.
_MIN_SILENCE_MS = 50_000
_MIN_KEEP_ALIVE_FRAMES = 3
_LIVENESS_BUDGET_MS = 45_000
_BUDGET_SLACK_MS = 5_000
_STALL_AFTER_MS = 4_000
# A page that never replaces the dead connection still gets its turn attached when its own read budget ends; the log is
# worth waiting for that long to report what the page did.
_STALL_LOG_TIMEOUT_SEC = 360.0


def _hold_hooks(out: Path, hold_sec: int) -> str:
    return f"""  PreToolUse:
    - script: 'sleep {hold_sec}'
      tools: [bash_*]
      timeout: {hold_sec + 30}
      description: Hold the run, with nothing to send, before the bash call runs.
"""


def _request() -> str:
    return (
        "Run exactly this one plain command with the bash tool, with no ';', '&&', pipe or redirect: echo HOOK-E2E-OK . "
        f"Run no other command. After it finishes, reply with exactly: {DONE_TOKEN}"
    )


def _run_held_turn(
    tmp_path: Path,
    ledger: E2EResourceLedger,
    *,
    hold_sec: int,
    judge: Callable[[StreamLog], None],
    stall_after_ms: int | None = None,
    log_timeout_sec: float = STREAM_END_TIMEOUT_SEC,
) -> None:
    """Run the held turn on a page the probe watches and have ``judge`` rule on what the page did with its streams.

    The ruling comes before the wait for the reply: a page that mishandled its streams may miss the reply as well, and the
    failure should then name the streams rather than the reply.
    """
    probe = setup_skill_chat(tmp_path, ledger, "silencehold", partial(_hold_hooks, hold_sec=hold_sec), yolo=True)

    def watch_until_the_turn_is_over(client: ChromeMcpClient, page: McpPage) -> None:
        judge(wait_for_stream_log(client, page, timeout_sec=log_timeout_sec))
        wait_for_reply_on_page(client, page, probe, "the page did not show the reply of the held turn")

    drive_chat_turn(
        get_e2e_ui_url(),
        probe,
        _request(),
        before_send=lambda client, page: install_stream_probe(client, page, stall_after_ms=stall_after_ms),
        while_open=watch_until_the_turn_is_over,
    )


def _the_held_silence(log: StreamLog) -> Silence:
    """The turn must really have been silent while the server sent its keep-alive frames, or the test proves nothing."""
    silence = longest_silence(log)
    assert silence is not None and silence.length_ms >= _MIN_SILENCE_MS, (
        f"the hook did not hold the stream silent: {silence}; {log}"
    )
    assert len(silence.heartbeats) >= _MIN_KEEP_ALIVE_FRAMES, f"the server sent too few keep-alive frames in {silence}; {log}"
    print(
        f"E2E_STREAM_SILENCE: {silence}; requests={log.requests}; loading_falls={loading_falls(log)}; watchdog={log.watchdog}",
        flush=True,
    )
    return silence


def _keep_alive_carries_the_silence(log: StreamLog) -> None:
    silence = _the_held_silence(log)
    opened_before_the_silence_ended = [request.kind for request in log.requests if request.at_ms < silence.end_ms]
    assert opened_before_the_silence_ended == ["run"], (
        f"the page needed more than its one request to get through a silence the server kept alive: {log}"
    )
    falls = loading_falls(log)
    assert falls and falls[0] >= silence.end_ms, (
        f"the page showed an idle chat while the turn was still silent: {falls}; {silence}; {log}"
    )
    assert not log.watchdog, f"the stream watchdog healed a turn the server kept alive: {log.watchdog}"


def _attach_stream_replaces_the_dead_connection(log: StreamLog) -> None:
    stalled = [chunk for chunk in log.chunks if chunk.kind == "stalled"]
    assert len(stalled) == 1, f"the probe did not stop the run stream exactly once: {log}"
    heard_until = last_heard(log, stalled[0].stream)
    attaches = [request for request in log.requests if request.kind == "attach"]
    falls = loading_falls(log)
    print(
        f"E2E_STREAM_STALL: stalled_at={stalled[0].at_ms} heard_until={heard_until} attaches={attaches} "
        f"loading_falls={falls} watchdog={log.watchdog}",
        flush=True,
    )

    assert attaches, f"the page never replaced the dead connection with an attach stream: {log}"
    recovery = attaches[0]
    waited_ms = recovery.at_ms - heard_until
    assert abs(waited_ms - _LIVENESS_BUDGET_MS) <= _BUDGET_SLACK_MS, (
        f"the page attached {waited_ms} ms after it last heard from the dead connection, not at its {_LIVENESS_BUDGET_MS} ms "
        f"liveness budget; the page was idle from {falls}; {log}"
    )

    # The server closes the attach stream when the turn is over; a stream the page cancelled never ends.
    recovery_ended_at = ended_at(log, recovery.stream)
    assert recovery_ended_at is not None, f"the page dropped the attach stream before the turn ended: {log}"
    reattached = [request for request in attaches[1:] if request.at_ms < recovery_ended_at]
    assert not reattached, f"the page opened more attach streams while the first one still carried the turn: {reattached}; {log}"

    attach_data = [chunk.at_ms for chunk in log.chunks if chunk.stream == recovery.stream and chunk.kind == "data"]
    assert falls and falls[0] >= max(attach_data), (
        f"the page showed an idle chat while the attach stream still carried data: {falls}; {log}"
    )

    silence = _the_held_silence(log)
    assert silence.start_ms >= recovery.at_ms, f"the longest silence is not the attach stream's: {silence}; {log}"
    assert not log.watchdog, f"the stream watchdog healed a turn that was recovered: {log.watchdog}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_keep_alive_frames_keep_the_page_busy_through_a_long_silence(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    _run_held_turn(tmp_path, e2e_resource_ledger, hold_sec=_HOLD_SEC, judge=_keep_alive_carries_the_silence)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_connection_that_stops_delivering_is_replaced_by_the_attach_stream_within_the_liveness_budget(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    _run_held_turn(
        tmp_path,
        e2e_resource_ledger,
        hold_sec=_STALL_HOLD_SEC,
        judge=_attach_stream_replaces_the_dead_connection,
        stall_after_ms=_STALL_AFTER_MS,
        log_timeout_sec=_STALL_LOG_TIMEOUT_SEC,
    )
