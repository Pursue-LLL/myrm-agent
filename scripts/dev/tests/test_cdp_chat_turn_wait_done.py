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
