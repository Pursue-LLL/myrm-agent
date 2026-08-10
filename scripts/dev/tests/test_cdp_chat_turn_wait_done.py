"""Unit tests for wait_turn_done / wait_turn_settled observation-chain fixes (§26.22)."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_turn import CdpChatTurn


def _turn() -> CdpChatTurn:
    turn = object.__new__(CdpChatTurn)
    # Sideload helper attributes the constructor would normally provide.
    turn._bridge_diag_last_emit = 0.0
    turn._goal_api_base_cached = ""
    return turn


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests hermetic: no live ledger, always non-LIVE profile."""
    monkeypatch.setattr("cdp_chat_turn.maybe_register_e2e_chat", lambda _chat_id: None)
    monkeypatch.setattr(
        "cdp_chat_turn.is_live_send_turn_profile", lambda: False
    )


async def _run(coro: Callable[[], object]) -> object:
    return await asyncio.wait_for(coro(), timeout=5.0)


def test_wait_turn_done_bridge_ok_returns_finish() -> None:
    """Bridge completion (hasCompletionSignal, not streaming) short-circuits."""
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "c1",
            "userCount": 1,
            "isStreaming": False,
            "hasCompletionSignal": True,
            "hasOk": True,
            "hasDone": False,
            "lastAssistantSample": "OK",
        }

    async def fake_goal(_chat_id: str) -> dict[str, object] | None:
        raise AssertionError("goal probe must not fire when bridge completes")

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn._goal_completion_if_persisted = fake_goal  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]

    result = asyncio.run(_run(lambda: turn.wait_turn_done("hi", chat_id_hint="c1")))
    assert result["chatId"] == "c1"
    assert result["okViaBridge"] is True
    assert result["okViaApi"] is False


def test_wait_turn_done_bridge_missing_but_dom_ok_recovers() -> None:
    """chat_id_hint blind spot fixed: bridge probe failing must not starve DOM fallback.

    Regression for the reported ``TimeoutError: ... OK: {}`` where the hint branch
    exhausted the shared deadline and never reached the DOM loop.
    """
    turn = _turn()
    bridge_calls = 0

    async def fake_bridge() -> dict[str, object] | None:
        nonlocal bridge_calls
        bridge_calls += 1
        if bridge_calls == 1:
            return None  # transport failure
        return {
            "chatId": "c1",
            "userCount": 1,
            "isStreaming": False,
            "hasCompletionSignal": False,
            "hasOk": False,
        }

    async def fake_main_state(_prompt: str, *, intent: object) -> dict[str, object]:
        return {"hasUserPrompt": True, "okInMain": True, "path": "/chat/c1"}

    async def fake_resolve(**kwargs: object) -> str | None:
        return "c1"

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn.main_state = fake_main_state  # type: ignore[method-assign]
    turn.resolve_chat_id = fake_resolve  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]
    turn.bridge_chat_id = AsyncMock(return_value="c1")  # type: ignore[method-assign]

    result = asyncio.run(
        _run(lambda: turn.wait_turn_done("hi", chat_id_hint="c1"))
    )
    assert result.get("okInMain") is True
    assert bridge_calls >= 1


def test_wait_turn_done_goal_signal_completes_without_ok_token() -> None:
    """Goal completion: bridge idle without OK token + persisted goal → okViaGoal."""
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "g1",
            "userCount": 1,
            "isStreaming": False,
            "hasCompletionSignal": False,
            "hasOk": False,
            "lastAssistantSample": "已开始调研目标",
        }

    async def fake_goal(_chat_id: str) -> dict[str, object] | None:
        return {"okViaGoal": True, "okViaApi": False, "goalStatus": "active"}

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn._goal_completion_if_persisted = fake_goal  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]

    result = asyncio.run(_run(lambda: turn.wait_turn_done("hi", chat_id_hint="g1")))
    assert result["chatId"] == "g1"
    assert result["okViaGoal"] is True
    assert result["goalStatus"] == "active"


def test_wait_turn_done_goal_none_does_not_fire_for_non_goal() -> None:
    """Non-Goal tests: goal probe returning None must never complete the turn."""
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "x1",
            "userCount": 1,
            "isStreaming": False,
            "hasCompletionSignal": False,
            "hasOk": False,
            "lastAssistantSample": "doing work",
        }

    async def fake_goal(_chat_id: str) -> dict[str, object] | None:
        return None  # no goal record → not a goal turn

    async def fake_main_state(_prompt: str, *, intent: object) -> dict[str, object]:
        return {"hasUserPrompt": False, "okInMain": False, "path": "/chat/x1"}

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn._goal_completion_if_persisted = fake_goal  # type: ignore[method-assign]
    turn.main_state = fake_main_state  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(TimeoutError, match="x1"):
        asyncio.run(
            _run(
                lambda: turn.wait_turn_done(
                    "hi", chat_id_hint="x1", timeout_sec=0.05
                )
            )
        )


def test_wait_turn_done_timeout_includes_latest_last() -> None:
    """Timeout diagnostics must carry the freshest observation, never empty {}."""
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "t1",
            "userCount": 1,
            "isStreaming": True,  # still streaming → no completion path
            "hasCompletionSignal": False,
            "lastAssistantSample": "in progress",
        }

    async def fake_main_state(_prompt: str, *, intent: object) -> dict[str, object]:
        return {
            "hasUserPrompt": True,
            "okInMain": False,
            "sending": True,
            "path": "/chat/t1",
            "sample": "in progress",
        }

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn.main_state = fake_main_state  # type: ignore[method-assign]
    turn.resolve_chat_id = AsyncMock(return_value="t1")  # type: ignore[method-assign]
    turn.bridge_chat_id = AsyncMock(return_value="t1")  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(TimeoutError) as excinfo:
        asyncio.run(
            _run(
                lambda: turn.wait_turn_done("hi", chat_id_hint="t1", timeout_sec=0.05)
            )
        )
    message = str(excinfo.value)
    assert "t1" in message
    assert "in progress" in message
    assert "Timed out waiting for assistant OK:" in message


def test_wait_turn_done_ok_in_main_ignored_while_bridge_streaming() -> None:
    """Regression: okInMain must NOT short-circuit while bridge reports streaming.

    The DOM main-text heuristic (page chrome can contain "OK" tokens) previously
    let wait_turn_done return before the assistant turn actually finished,
    stranding wait_input_empty on a still-streaming bridge. When the bridge
    probe succeeds with isStreaming=True, the DOM fallback must wait instead.
    """
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "s2",
            "userCount": 1,
            "isStreaming": True,
            "hasCompletionSignal": False,
            "hasOk": False,
            "lastAssistantSample": "",
        }

    async def fake_main_state(_prompt: str, *, intent: object) -> dict[str, object]:
        return {
            "hasUserPrompt": True,
            "okInMain": True,  # misleading: page chrome contains "OK"
            "sending": False,
            "path": "/chat/s2",
            "sample": "…OK…",
        }

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn.main_state = fake_main_state  # type: ignore[method-assign]
    turn.resolve_chat_id = AsyncMock(return_value="s2")  # type: ignore[method-assign]
    turn.bridge_chat_id = AsyncMock(return_value="s2")  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]

    with pytest.raises(TimeoutError, match="s2"):
        asyncio.run(
            _run(
                lambda: turn.wait_turn_done("hi", chat_id_hint="s2", timeout_sec=0.05)
            )
        )


def test_wait_turn_done_ok_in_main_still_allowed_when_bridge_null() -> None:
    """DOM okInMain fallback remains reachable when the bridge probe fails."""
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return None  # transport failure → bridge_streaming=False

    async def fake_main_state(_prompt: str, *, intent: object) -> dict[str, object]:
        return {"hasUserPrompt": True, "okInMain": True, "path": "/chat/d1"}

    async def fake_resolve(**kwargs: object) -> str | None:
        return "d1"

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn.main_state = fake_main_state  # type: ignore[method-assign]
    turn.resolve_chat_id = fake_resolve  # type: ignore[method-assign]
    turn.bridge_chat_id = AsyncMock(return_value="d1")  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]

    result = asyncio.run(
        _run(lambda: turn.wait_turn_done("hi", chat_id_hint="d1"))
    )
    assert result.get("okInMain") is True


def test_wait_turn_settled_dom_fallback_when_bridge_null() -> None:
    """wait_turn_settled recovers from persistent bridge failure via DOM probe."""
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return None  # bridge never available

    async def fake_main_state(_prompt: str, *, intent: object) -> dict[str, object]:
        return {
            "userMsgs": 1,
            "sending": False,
            "path": "/chat/s1",
            "assistantSample": "settled reply",
        }

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn.main_state = fake_main_state  # type: ignore[method-assign]
    turn.resolve_chat_id = AsyncMock(return_value="s1")  # type: ignore[method-assign]

    result = asyncio.run(
        _run(lambda: turn.wait_turn_settled(chat_id_hint="s1"))
    )
    assert result["chatId"] == "s1"
    assert result["okViaBridge"] is True


def test_bridge_diag_throttles_and_tags_transport_error() -> None:
    """TRANSPORT_ERR diag emitted; throttled to 1 per 10s window."""
    turn = _turn()
    emitted: list[str] = []

    async def fake_evaluate(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("Target closed")

    turn.evaluate = fake_evaluate  # type: ignore[method-assign]
    with patch("builtins.print", side_effect=lambda *args, **kwargs: emitted.append(str(args[0]))):
        asyncio.run(turn._bridge_turn_snapshot())
    assert emitted and "TRANSPORT_ERR" in emitted[0]

    # Throttle: second emit within 10s window must be suppressed.
    with patch("builtins.print", side_effect=lambda *args, **kwargs: emitted.append(str(args[0]))):
        asyncio.run(turn._bridge_turn_snapshot())
    assert len(emitted) == 1


def test_bridge_diag_js_null_tagged() -> None:
    """JS returning null (bridge not mounted) yields a JS_NULL diagnostic token."""
    turn = _turn()

    async def fake_evaluate(*_args: object, **_kwargs: object) -> object:
        return None

    emitted: list[str] = []
    turn.evaluate = fake_evaluate  # type: ignore[method-assign]
    with patch("builtins.print", side_effect=lambda *args, **kwargs: emitted.append(str(args[0]))):
        asyncio.run(turn._bridge_turn_snapshot())
    assert emitted and "JS_NULL" in emitted[0]


def test_goal_api_base_cache_and_fallback() -> None:
    """Bound page API base wins; empty/missing binding falls back to env default."""
    turn = _turn()
    call_order: list[str] = []

    async def fake_evaluate(expression: str, *, intent: object) -> object:
        call_order.append("evaluate")
        if "__MYRM_E2E_API_BASE__" in expression:
            return "http://127.0.0.1:18095"
        return None

    turn.evaluate = fake_evaluate  # type: ignore[method-assign]
    with patch("cdp_chat_turn.cdp_chat_support.get_e2e_api_url", return_value="http://127.0.0.1:8080"):
        base = asyncio.run(turn._resolved_goal_api_base())
    assert base == "http://127.0.0.1:18095"
    assert turn._goal_api_base_cached == "http://127.0.0.1:18095"
    # Cached: second call must not re-evaluate.
    asyncio.run(turn._resolved_goal_api_base())
    assert call_order.count("evaluate") == 1

    fallback = _turn()
    async def fake_evaluate_none(*_args: object, **_kwargs: object) -> object:
        return None

    fallback.evaluate = fake_evaluate_none  # type: ignore[method-assign]
    with patch("cdp_chat_turn.cdp_chat_support.get_e2e_api_url", return_value="http://127.0.0.1:8080"):
        base = asyncio.run(fallback._resolved_goal_api_base())
    assert base == "http://127.0.0.1:8080"


def test_goal_completion_probe_uses_bound_api_base() -> None:
    """Goal probe passes resolved api base and honors None record."""
    turn = _turn()
    turn._goal_api_base_cached = "http://127.0.0.1:18095"

    with patch(
        "cdp_chat_turn.cdp_chat_support.fetch_e2e_goal_status",
        return_value={"status": "active", "objective": "x"},
    ) as mock_fetch:
        result = asyncio.run(turn._goal_completion_if_persisted("g1"))
    mock_fetch.assert_called_once_with("g1", api_url="http://127.0.0.1:18095")
    assert result is not None
    assert result["okViaGoal"] is True
    assert result["goalStatus"] == "active"

    with patch(
        "cdp_chat_turn.cdp_chat_support.fetch_e2e_goal_status",
        return_value=None,
    ):
        assert asyncio.run(turn._goal_completion_if_persisted("g1")) is None


def test_goal_completion_rejects_empty_objective() -> None:
    """Stub goal records without objective must not complete the turn."""
    turn = _turn()
    turn._goal_api_base_cached = "http://127.0.0.1:18095"

    with patch(
        "cdp_chat_turn.cdp_chat_support.fetch_e2e_goal_status",
        return_value={"status": "active", "objective": ""},
    ):
        assert asyncio.run(turn._goal_completion_if_persisted("g1")) is None


def test_goal_completion_rejects_unknown_status() -> None:
    """Goal probe must align with Goal E2E status allow-list."""
    turn = _turn()
    turn._goal_api_base_cached = "http://127.0.0.1:18095"

    with patch(
        "cdp_chat_turn.cdp_chat_support.fetch_e2e_goal_status",
        return_value={"status": "pending", "objective": "research topic"},
    ):
        assert asyncio.run(turn._goal_completion_if_persisted("g1")) is None


def test_wait_turn_done_chat_id_hint_used_when_bridge_null_first() -> None:
    """chat_id_hint must be bound before bridge probe so goal/API paths never see unbound locals."""
    turn = _turn()
    goal_calls: list[str] = []

    async def fake_bridge() -> dict[str, object] | None:
        return None

    async def fake_goal(chat_id: str) -> dict[str, object] | None:
        goal_calls.append(chat_id)
        return None

    async def fake_main_state(_prompt: str, *, intent: object) -> dict[str, object]:
        return {"hasUserPrompt": False, "okInMain": False, "path": "/chat/h1"}

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn._goal_completion_if_persisted = fake_goal  # type: ignore[method-assign]
    turn.main_state = fake_main_state  # type: ignore[method-assign]
    turn._finish_if_api_ok = AsyncMock(return_value=None)  # type: ignore[method-assign]
    turn.bridge_chat_id = AsyncMock(return_value="h1")  # type: ignore[method-assign]

    with pytest.raises(TimeoutError, match="h1"):
        asyncio.run(
            _run(
                lambda: turn.wait_turn_done("hi", chat_id_hint="h1", timeout_sec=0.05)
            )
        )
    assert goal_calls == []


def test_wait_e2e_goal_status_skips_non_persisted_records() -> None:
    """Poll must ignore stub goals until objective+status match SSOT."""
    from cdp_chat_support import wait_e2e_goal_status

    calls = {"n": 0}

    def fake_fetch(_chat_id: str, *, api_url: str | None = None) -> dict[str, object] | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return {"status": "active", "objective": ""}
        return {"status": "active", "objective": "research topic"}

    with patch("cdp_chat_support.fetch_e2e_goal_status", side_effect=fake_fetch):
        with patch("cdp_chat_support.time.sleep", return_value=None):
            goal = wait_e2e_goal_status("g1", timeout_sec=5.0, poll_interval_sec=0.01)
    assert goal is not None
    assert goal.get("objective") == "research topic"
    assert calls["n"] == 2


def test_wait_input_empty_normal_completed_turn_returns_immediately() -> None:
    """Completed turn (no Stop button, empty input, not streaming) must return fast.

    Regression for the repeated ``Chat input not ready for send`` LIVE failures
    where the old code required ``not sendDisabled`` — but the frontend send
    button is inherently disabled when the input is empty, so the completed
    state (inputLen=0 + sendDisabled=true) could never satisfy it.
    """
    turn = _turn()

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "c1",
            "userCount": 1,
            "isStreaming": False,
            "hasCompletionSignal": True,
            "hasOk": True,
        }

    async def fake_dom() -> dict[str, object]:
        # Completed turn: no Stop button, input already cleared.
        return {"sending": False, "inputLen": 0, "hasStopBtn": False}

    async def fake_send_state() -> dict[str, object]:
        return {"ok": False, "inputLen": 0, "sendDisabled": True}

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn._dom_state = fake_dom  # type: ignore[method-assign]
    turn.send_state = fake_send_state  # type: ignore[method-assign]
    cleared = {"n": 0}

    async def fake_clear() -> None:
        cleared["n"] += 1

    turn._clear_input_via_bridge = fake_clear  # type: ignore[method-assign]
    with patch(
        "cdp_chat_turn.chat_messages_have_ok",
        return_value=True,
    ):
        asyncio.run(
            _run(lambda: turn.wait_input_empty(chat_id_hint="c1", timeout_sec=2.0))
        )
    # API confirms OK → clears then returns; must not hang to timeout.
    assert cleared["n"] == 1


def test_wait_input_empty_waits_while_stop_button_present() -> None:
    """While loading (Stop button in DOM) the wait must keep polling, not return."""
    turn = _turn()
    state = {"loading": True}

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "c1",
            "userCount": 1,
            "isStreaming": state["loading"],
            "hasCompletionSignal": True,
        }

    async def fake_dom() -> dict[str, object]:
        return {"sending": state["loading"], "inputLen": 0, "hasStopBtn": state["loading"]}

    async def fake_send_state() -> dict[str, object]:
        return {"ok": False, "inputLen": 0, "sendDisabled": True}

    async def fake_evaluate(*_args: object, **_kwargs: object) -> object:
        return None

    calls = {"n": 0}

    async def fake_clear() -> None:
        calls["n"] += 1

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn._dom_state = fake_dom  # type: ignore[method-assign]
    turn.send_state = fake_send_state  # type: ignore[method-assign]
    turn._clear_input_via_bridge = fake_clear  # type: ignore[method-assign]
    turn.evaluate = fake_evaluate  # type: ignore[method-assign]

    async def flipper() -> None:
        await asyncio.sleep(0.05)
        state["loading"] = False

    async def scenario() -> None:
        task = asyncio.create_task(
            turn.wait_input_empty(chat_id_hint="c1", timeout_sec=2.0)
        )
        await flipper()
        await task

    with patch(
        "cdp_chat_turn.chat_messages_have_ok",
        return_value=False,
    ):
        asyncio.run(scenario())
    assert calls["n"] == 0


def test_wait_input_empty_clears_residual_text_when_not_loading() -> None:
    """Residual input text (not loading) is cleared then returns."""
    turn = _turn()
    cleared = {"n": 0}

    async def fake_bridge() -> dict[str, object] | None:
        return {
            "chatId": "c1",
            "userCount": 1,
            "isStreaming": False,
            "hasCompletionSignal": True,
        }

    async def fake_dom() -> dict[str, object]:
        return {"sending": False, "inputLen": 3, "hasStopBtn": False}

    sends = {"n": 0}

    async def fake_send_state() -> dict[str, object]:
        sends["n"] += 1
        if sends["n"] == 1:
            return {"ok": False, "inputLen": 3, "sendDisabled": False}
        return {"ok": False, "inputLen": 0, "sendDisabled": True}

    async def fake_clear() -> None:
        cleared["n"] += 1

    turn._bridge_turn_snapshot = fake_bridge  # type: ignore[method-assign]
    turn._dom_state = fake_dom  # type: ignore[method-assign]
    turn.send_state = fake_send_state  # type: ignore[method-assign]
    turn._clear_input_via_bridge = fake_clear  # type: ignore[method-assign]

    with patch(
        "cdp_chat_turn.chat_messages_have_ok",
        return_value=False,
    ):
        asyncio.run(
            _run(lambda: turn.wait_input_empty(chat_id_hint="c1", timeout_sec=2.0))
        )
    assert cleared["n"] == 1
