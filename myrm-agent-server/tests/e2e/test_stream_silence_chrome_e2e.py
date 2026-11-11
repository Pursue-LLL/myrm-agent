"""A turn the server holds silent for over a minute keeps the page busy exactly as long as the server's keep-alive frames reach it.

A skill's PreToolUse hook sleeps before the model's bash call runs. The pre-call guards run before the tool's own heartbeat task
starts, so for that stretch the real turn sends nothing: the server answers only with its keep-alive frame every 15 s. Both tests
run the same real turn against the same real wire; they differ in whether the page's stream consumer is shown those frames.

- With them, the chat stays busy (``loading``) through the whole silence and the stream watchdog never heals it.
- Without them (swallowed in the page, as a proxy that eats them would), the watchdog ends the busy state after its window of
  silence (45 s, three keep-alive intervals): a transport that died cannot keep the page busy for ever.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url
from tests.support.chrome_skill_hooks_composer import drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, setup_skill_chat
from tests.support.e2e_runtime_guard import E2EResourceLedger
from tests.support.stream_silence import (
    Silence,
    StreamLog,
    install_stream_probe,
    loading_falls,
    longest_silence,
    wait_for_stream_log,
)

_HOLD_SEC = 70
# The hold minus the model's own pauses on either side of it; three keep-alive intervals fit in it.
_MIN_SILENCE_MS = 50_000
_MIN_KEEP_ALIVE_FRAMES = 3
_WINDOW_MS = 45_000
_WINDOW_SLACK_MS = 5_000


def _hold_hooks(out: Path) -> str:
    return f"""  PreToolUse:
    - script: 'sleep {_HOLD_SEC}'
      tools: [bash_*]
      timeout: {_HOLD_SEC + 30}
      description: Hold the run, with nothing to send, before the bash call runs.
"""


def _request() -> str:
    return (
        "Run exactly this one plain command with the bash tool, with no ';', '&&', pipe or redirect: echo HOOK-E2E-OK . "
        f"Run no other command. After it finishes, reply with exactly: {DONE_TOKEN}"
    )


def _run_held_turn(tmp_path: Path, ledger: E2EResourceLedger, *, swallow_heartbeats: bool) -> StreamLog:
    probe = setup_skill_chat(tmp_path, ledger, "silencehold", _hold_hooks, yolo=True)
    logs: list[StreamLog] = []
    drive_chat_turn(
        get_e2e_ui_url(),
        probe,
        _request(),
        before_send=lambda client, page: install_stream_probe(client, page, swallow_heartbeats=swallow_heartbeats),
        while_open=lambda client, page: logs.append(wait_for_stream_log(client, page)),
    )
    return logs[0]


def _the_held_silence(log: StreamLog) -> Silence:
    """The turn must really have been silent while the server sent its keep-alive frames, or the test proves nothing."""
    silence = longest_silence(log)
    assert silence is not None and silence.length_ms >= _MIN_SILENCE_MS, (
        f"the hook did not hold the stream silent: {silence}; {log}"
    )
    assert len(silence.heartbeats) >= _MIN_KEEP_ALIVE_FRAMES, f"the server sent too few keep-alive frames in {silence}; {log}"
    print(f"E2E_STREAM_SILENCE: {silence}; loading_falls={loading_falls(log)}; watchdog={log.watchdog}", flush=True)
    return silence


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
    log = _run_held_turn(tmp_path, e2e_resource_ledger, swallow_heartbeats=False)
    silence = _the_held_silence(log)
    falls = loading_falls(log)
    assert falls and falls[0] >= silence.end_ms, (
        f"the page showed an idle chat while the turn was still silent: {falls}; {silence}; {log}"
    )
    assert not log.watchdog, f"the stream watchdog healed a turn the server kept alive: {log.watchdog}"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_silence_the_page_is_never_told_about_ends_the_busy_state_after_the_window(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    log = _run_held_turn(tmp_path, e2e_resource_ledger, swallow_heartbeats=True)
    silence = _the_held_silence(log)
    falls = loading_falls(log)
    assert falls, f"the page stayed busy through a silence it was never told about: {silence}; {log}"
    waited_ms = falls[0] - silence.start_ms
    assert abs(waited_ms - _WINDOW_MS) <= _WINDOW_SLACK_MS, (
        f"the page healed {waited_ms} ms into the silence, not at its {_WINDOW_MS} ms window; {log}"
    )
    assert any("silence timeout" in line for line in log.watchdog), f"the busy state ended without the watchdog: {log}"
