"""Unit tests for fast_search_turn: the fast-mode proof has to fail on every way a turn can leave fast mode."""

from __future__ import annotations

import json

import pytest

from tests.support import fast_search_turn
from tests.support.fast_search_turn import run_fast_search_turn

_PROMPT = '请搜索 "Python 3.14"，不要改写'


class _ScriptedPage:
    """A page that answers the helper's scripts from fixed values and records the sends."""

    def __init__(
        self,
        *,
        mode_before: str = "fast",
        mode_after: str = "fast",
        wire: tuple[str, ...] = ("fast",),
        assistants: int = 1,
        send_ok: bool = True,
        completes: bool = True,
    ) -> None:
        self._modes = {"before": mode_before, "after": mode_after}
        self._wire = list(wire)
        self._assistants = assistants
        self._send_ok = send_ok
        self._completes = completes
        self._probes = 0
        self.sent_scripts: list[str] = []

    async def evaluate(self, expression: str, *, await_promise: bool = True) -> object:
        if expression == fast_search_turn._WIRE_MODES_JS:
            return list(self._wire)
        if expression == fast_search_turn._TURN_STATE_JS:
            return {"assistants": self._assistants, "completed": self._completes, "loading": False}
        if expression == fast_search_turn._PAGE_PROBE_JS:
            self._probes += 1
            mode = self._modes["before"] if self._probes == 1 else self._modes["after"]
            return {"chatId": "chat-1", "actionMode": mode, "lastSubmit": {"ok": True, "err": None, "mode": "sendTurnSealed"}}
        if "sendChatMessage" in expression:
            self.sent_scripts.append(expression)
            return {"ok": self._send_ok}
        raise AssertionError(f"unexpected page script: {expression[:80]}")


@pytest.fixture(autouse=True)
def _no_heartbeat_and_no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fast_search_turn, "heartbeat_once", lambda: None)
    monkeypatch.setattr(fast_search_turn, "_POLL_INTERVAL_SEC", 0.0)


async def test_a_fast_turn_returns_the_page_state_and_sends_the_prompt_unchanged(capsys: pytest.CaptureFixture[str]) -> None:
    page = _ScriptedPage()

    state = await run_fast_search_turn(page, _PROMPT, turn=1, timeout_sec=5.0)

    assert state["chatId"] == "chat-1"
    assert len(page.sent_scripts) == 1
    assert json.dumps(_PROMPT) in page.sent_scripts[0]
    assert fast_search_turn._PROMPT_PLACEHOLDER not in page.sent_scripts[0]
    assert "wire=['fast']" in capsys.readouterr().out


async def test_a_second_fast_turn_passes_with_two_fast_requests() -> None:
    page = _ScriptedPage(wire=("fast", "fast"), assistants=2)

    assert (await run_fast_search_turn(page, _PROMPT, turn=2, timeout_sec=5.0))["chatId"] == "chat-1"


async def test_a_chat_that_is_not_in_fast_mode_never_sends() -> None:
    page = _ScriptedPage(mode_before="agent")

    with pytest.raises(AssertionError, match="was not in fast mode"):
        await run_fast_search_turn(page, _PROMPT, turn=1, timeout_sec=5.0)

    assert page.sent_scripts == []


async def test_a_chat_that_leaves_fast_mode_during_the_turn_fails() -> None:
    page = _ScriptedPage(mode_after="agent")

    with pytest.raises(AssertionError, match="left fast mode"):
        await run_fast_search_turn(page, _PROMPT, turn=1, timeout_sec=5.0)


@pytest.mark.parametrize(
    ("wire", "turn", "assistants"),
    [
        pytest.param(("agent",), 1, 1, id="request-in-another-mode"),
        pytest.param(("fast", "agent"), 2, 2, id="second-request-in-another-mode"),
        pytest.param((), 1, 1, id="no-request-recorded"),
        pytest.param(("fast",), 2, 2, id="no-request-for-the-second-turn"),
    ],
)
async def test_a_request_that_did_not_go_out_in_fast_mode_fails(wire: tuple[str, ...], turn: int, assistants: int) -> None:
    page = _ScriptedPage(wire=wire, assistants=assistants)

    with pytest.raises(AssertionError, match="did not go out in fast mode"):
        await run_fast_search_turn(page, _PROMPT, turn=turn, timeout_sec=5.0)


async def test_a_send_that_was_not_issued_fails() -> None:
    page = _ScriptedPage(send_ok=False)

    with pytest.raises(AssertionError, match="send was not issued"):
        await run_fast_search_turn(page, _PROMPT, turn=1, timeout_sec=5.0)


async def test_a_turn_that_never_completes_times_out_with_the_page_state() -> None:
    page = _ScriptedPage(completes=False)

    with pytest.raises(TimeoutError, match="turn 1 did not complete") as raised:
        await run_fast_search_turn(page, _PROMPT, turn=1, timeout_sec=0.05)

    assert "chat-1" in str(raised.value)
