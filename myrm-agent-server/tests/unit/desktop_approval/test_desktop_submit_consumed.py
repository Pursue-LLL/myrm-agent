"""Unit tests for fast_desktop_agent_submit consume-verify + refill (R-ax15/ax16).

Covers CdpChatTurn.fast_desktop_agent_submit without Chrome: the initial
native click may report ok while nothing persists server-side (mux reclaim
wiping the filled input). The submit must re-fill + re-click once, and fail
fast when the turn stays silent.
"""
from __future__ import annotations

import cdp_chat.turn as turn_module
import pytest
from cdp_chat.turn import CdpChatTurn


def _make_chat(
    *,
    wait_outcomes: list[object],
    submit_outcomes: list[dict[str, object]] | None = None,
    api_counts: list[int] | None = None,
    bridge_outcomes: list[object] | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> CdpChatTurn:
    if monkeypatch is not None:
        # Keep the API grace loop millisecond-scale in unit tests.
        monkeypatch.setattr(turn_module, "_SUBMIT_API_GRACE_SEC", 0.05)
        monkeypatch.setattr(turn_module, "_SUBMIT_API_GRACE_POLL_SEC", 0.001)
    chat = CdpChatTurn.__new__(CdpChatTurn)
    state = {
        "wait_calls": 0,
        "submit_calls": 0,
        "bridge_calls": 0,
        "evaluate_calls": 0,
        "diags": [],
    }
    object.__setattr__(chat, "_unit_state", state)

    async def _ensure_bridge(*_: object, **__: object) -> None:
        return None

    async def _evaluate(*_: object, **__: object) -> dict[str, object]:
        state["evaluate_calls"] += 1
        return {"ok": True}

    async def _submit_native_click(*_: object, **__: object) -> dict[str, object]:
        state["submit_calls"] += 1
        if submit_outcomes:
            return submit_outcomes.pop(0)
        return {"ok": True, "mode": "nativeClick"}

    async def _submit_via_dev_bridge(*_: object, **__: object) -> dict[str, object]:
        state["bridge_calls"] += 1
        if bridge_outcomes is None:
            raise AssertionError("unexpected bridge primary submit")
        if not bridge_outcomes:
            raise AssertionError("missing bridge submit outcome")
        current = bridge_outcomes.pop(0)
        if isinstance(current, BaseException):
            raise current
        assert isinstance(current, dict)
        return current

    async def _wait_stream_started(*_: object, **__: object) -> dict[str, object]:
        state["wait_calls"] += 1
        if not wait_outcomes:
            raise AssertionError("missing wait_stream_started outcome")
        current = wait_outcomes.pop(0)
        if isinstance(current, BaseException):
            raise current
        assert isinstance(current, dict)
        return current

    def _emit_diag(message: str) -> None:
        state["diags"].append(message)

    pending_counts = list(api_counts) if api_counts is not None else []

    async def _best_effort_count(*_: object, **__: object) -> int:
        if not pending_counts:
            raise AssertionError("unexpected api user count outcome")
        if len(pending_counts) > 1:
            return pending_counts.pop(0)
        return pending_counts[0]

    async def _main_state(*_: object, **__: object) -> dict[str, object]:
        return {
            "userMsgs": 0,
            "sending": False,
            "hasUserPrompt": False,
            "bridgeChatId": "chat-1",
            "path": "/chat/chat-1",
            "sample": "",
        }

    object.__setattr__(chat, "_best_effort_user_message_count", _best_effort_count)
    object.__setattr__(chat, "_submit_via_dev_bridge", _submit_via_dev_bridge)
    object.__setattr__(chat, "main_state", _main_state)
    object.__setattr__(chat, "ensure_react_e2e_bridge", _ensure_bridge)
    object.__setattr__(chat, "evaluate", _evaluate)
    object.__setattr__(chat, "submit_native_click", _submit_native_click)
    object.__setattr__(chat, "wait_stream_started", _wait_stream_started)
    object.__setattr__(chat, "_emit_bridge_diag", _emit_diag)
    return chat


@pytest.mark.asyncio
async def test_submit_consumed_first_try_no_refill() -> None:
    # Bridge atomic seals: native click never fires, no API grace probe
    # may run (api stub raises).
    chat = _make_chat(
        wait_outcomes=[{"okViaApi": True, "userMsgs": 1}],
        bridge_outcomes=[{"ok": True, "mode": "sendTurnSealed", "chatId": "chat-9"}],
    )
    result = await chat.fast_desktop_agent_submit(
        "do stuff",
        "do stuff",
        baseline_user_msgs_hint=0,
    )
    submit = result.get("submit")
    assert isinstance(submit, dict)
    assert submit.get("primary") == "bridgeAtomic"
    assert submit.get("mode") == "sendTurnSealed"
    started = result.get("started")
    assert isinstance(started, dict)
    assert started.get("streamProbe", "") != "consumed_after_refill"
    state = chat._unit_state  # noqa: SLF001
    assert state["wait_calls"] == 1
    assert state["submit_calls"] == 0
    assert state["bridge_calls"] == 1


@pytest.mark.asyncio
async def test_submit_bridge_miss_falls_back_to_native() -> None:
    chat = _make_chat(
        wait_outcomes=[{"okViaApi": True, "userMsgs": 1}],
        bridge_outcomes=[
            {"ok": False, "err": "send-not-ready", "mode": "sendTurnNotReady"}
        ],
    )
    result = await chat.fast_desktop_agent_submit(
        "do stuff",
        "do stuff",
        baseline_user_msgs_hint=0,
    )
    submit = result.get("submit")
    assert isinstance(submit, dict)
    assert submit.get("mode") == "nativeClick"
    assert "primary" not in submit
    state = chat._unit_state  # noqa: SLF001
    assert state["bridge_calls"] == 1
    assert state["submit_calls"] == 1
    assert any("BRIDGE_PRIMARY_MISS" in diag for diag in state["diags"])


@pytest.mark.asyncio
async def test_submit_bridge_transport_error_falls_back_to_native() -> None:
    chat = _make_chat(
        wait_outcomes=[{"okViaApi": True, "userMsgs": 1}],
        bridge_outcomes=[RuntimeError("mux gone")],
    )
    result = await chat.fast_desktop_agent_submit(
        "do stuff",
        "do stuff",
        baseline_user_msgs_hint=0,
    )
    assert result.get("submit", {}).get("mode") == "nativeClick"
    state = chat._unit_state  # noqa: SLF001
    assert state["bridge_calls"] == 1
    assert state["submit_calls"] == 1


@pytest.mark.asyncio
async def test_submit_silent_then_refill_consumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = _make_chat(
        wait_outcomes=[
            TimeoutError("UI send did not start stream"),
            {"okViaApi": True, "userMsgs": 1},
        ],
        api_counts=[0],
        bridge_outcomes=[
            {"ok": False, "err": "send-not-ready", "mode": "sendTurnNotReady"},
            {"ok": True, "mode": "sendTurnSealed", "chatId": "chat-1"},
        ],
        monkeypatch=monkeypatch,
    )
    result = await chat.fast_desktop_agent_submit(
        "do stuff",
        "do stuff",
        chat_id_hint="chat-1",
        baseline_user_msgs_hint=0,
    )
    started = result.get("started")
    assert isinstance(started, dict)
    assert started.get("streamProbe") == "consumed_after_refill"
    submit = result.get("submit")
    assert isinstance(submit, dict)
    assert submit.get("primary") == "bridgeAtomicRefill"
    state = chat._unit_state  # noqa: SLF001
    assert state["wait_calls"] == 2
    assert state["submit_calls"] == 1
    assert state["bridge_calls"] == 2
    assert any("SUBMIT_NOT_CONSUMED" in diag for diag in state["diags"])


@pytest.mark.asyncio
async def test_submit_silent_twice_raises_fail_fast_with_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = _make_chat(
        wait_outcomes=[
            TimeoutError("UI send did not start stream"),
            TimeoutError("UI send did not start stream"),
        ],
        api_counts=[0, 0],
        bridge_outcomes=[
            {"ok": False, "err": "send-not-ready", "mode": "sendTurnNotReady"},
            {"ok": False, "err": "chat-still-busy", "mode": "sendTurnBusy"},
        ],
        monkeypatch=monkeypatch,
    )
    with pytest.raises(RuntimeError, match="not consumed after refill") as excinfo:
        await chat.fast_desktop_agent_submit(
            "do stuff",
            "do stuff",
            chat_id_hint="chat-1",
            baseline_user_msgs_hint=0,
        )
    message = str(excinfo.value)
    assert "final=" in message
    assert "apiUsers" in message
    state = chat._unit_state  # noqa: SLF001
    assert state["wait_calls"] == 2
    assert state["submit_calls"] == 2
    assert state["bridge_calls"] == 2


@pytest.mark.asyncio
async def test_submit_ui_sending_flag_without_persistence_triggers_refill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R-ax19/ax21: stuck UI flags alone must not count as consumed."""
    chat = _make_chat(
        wait_outcomes=[
            {"sending": True, "userMsgs": 0},
            {"okViaApi": True, "userMsgs": 1},
        ],
        api_counts=[0],
        bridge_outcomes=[
            {"ok": False, "err": "send-not-ready", "mode": "sendTurnNotReady"},
            {"ok": True, "mode": "sendTurnSealed", "chatId": "chat-1"},
        ],
        monkeypatch=monkeypatch,
    )
    result = await chat.fast_desktop_agent_submit(
        "do stuff",
        "do stuff",
        chat_id_hint="chat-1",
        baseline_user_msgs_hint=0,
    )
    started = result.get("started")
    assert isinstance(started, dict)
    assert started.get("streamProbe") == "consumed_after_refill"
    state = chat._unit_state  # noqa: SLF001
    assert state["wait_calls"] == 2
    assert state["submit_calls"] == 1
    assert state["bridge_calls"] == 2


@pytest.mark.asyncio
async def test_submit_slow_api_backstop_accepts_without_refill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slow API: UI wait inconclusive but message landed -> no double-send."""
    chat = _make_chat(
        wait_outcomes=[{"sending": True, "userMsgs": 0}],
        api_counts=[0, 0, 1],
        bridge_outcomes=[
            {"ok": False, "err": "send-not-ready", "mode": "sendTurnNotReady"}
        ],
        monkeypatch=monkeypatch,
    )
    result = await chat.fast_desktop_agent_submit(
        "do stuff",
        "do stuff",
        chat_id_hint="chat-1",
        baseline_user_msgs_hint=0,
    )
    started = result.get("started")
    assert isinstance(started, dict)
    assert started.get("chatId") == "chat-1"
    state = chat._unit_state  # noqa: SLF001
    assert state["wait_calls"] == 1
    assert state["submit_calls"] == 1


@pytest.mark.asyncio
async def test_submit_timeout_with_api_persisted_accepts_backstop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat = _make_chat(
        wait_outcomes=[TimeoutError("UI send did not start stream")],
        api_counts=[2],
        bridge_outcomes=[
            {"ok": False, "err": "send-not-ready", "mode": "sendTurnNotReady"}
        ],
        monkeypatch=monkeypatch,
    )
    result = await chat.fast_desktop_agent_submit(
        "do stuff",
        "do stuff",
        chat_id_hint="chat-1",
        baseline_user_msgs_hint=1,
    )
    started = result.get("started")
    assert isinstance(started, dict)
    assert started.get("okViaApiBackstop") is True
    assert started.get("chatId") == "chat-1"
    state = chat._unit_state  # noqa: SLF001
    assert state["wait_calls"] == 1
    assert state["submit_calls"] == 1


@pytest.mark.asyncio
async def test_submit_no_wait_flag_unchanged_fire_and_forget() -> None:
    # Nudge path: bridge primary must never fire.
    chat = _make_chat(wait_outcomes=[], bridge_outcomes=[])
    result = await chat.fast_desktop_agent_submit(
        "nudge",
        "nudge",
        baseline_user_msgs_hint=0,
        wait_stream_started=False,
    )
    assert result.get("started", {}).get("streamProbe") == "skipped_for_follow_up_nudge"
    state = chat._unit_state  # noqa: SLF001
    assert state["wait_calls"] == 0
    assert state["submit_calls"] == 1
