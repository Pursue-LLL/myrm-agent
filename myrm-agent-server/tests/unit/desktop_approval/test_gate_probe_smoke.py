"""Unit smoke tests for desktop approval gate probe helpers."""

from __future__ import annotations

import asyncio

import pytest

from tests.e2e.desktop_approval.gate_probe import (
    _build_fallback_budget,
    _DesktopFallbackBudget,
    _ensure_nudge_chat_surface_guarded,
    _merge_desktop_progress,
    _record_pending_seed_fallback,
    _record_synthetic_dref_fallback,
    _send_interact_nudge,
    _wait_desktop_tool_activity_failfast,
    _wait_nudge_send_surface,
    interact_without_gate_handoff_elapsed,
    require_approval_gate_triggered,
    snapshot_loop_stuck_sec,
)


class _DummyChat:
    pass


class _SurfaceProbeChat:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def ensure_react_e2e_bridge(self, *, timeout_sec: float) -> None:
        _ = timeout_sec
        self.calls.append("ensure_react_e2e_bridge")

    async def wait_send_button_ready(self, *, timeout_sec: float) -> dict[str, object]:
        _ = timeout_sec
        self.calls.append("wait_send_button_ready")
        return {"ok": True}


class _NudgeRetryChat:
    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.submit_calls = 0

    async def fast_desktop_agent_submit(
        self,
        *_: object,
        **__: object,
    ) -> dict[str, object]:
        self.submit_calls += 1
        if not self._outcomes:
            raise AssertionError("missing fast_desktop_agent_submit outcome")
        current = self._outcomes.pop(0)
        if isinstance(current, Exception):
            raise current
        if isinstance(current, dict):
            return current
        raise AssertionError(f"unexpected submit outcome: {current!r}")


def test_require_approval_gate_triggered_passes_when_pending() -> None:
    require_approval_gate_triggered(
        last_tool="",
        server_pending=1,
        ui_pending=False,
    )


def test_require_approval_gate_triggered_fails_when_idle() -> None:
    with pytest.raises(AssertionError, match="snapshot/vision loop"):
        require_approval_gate_triggered(
            last_tool="desktop_snapshot_tool",
            server_pending=0,
            ui_pending=False,
            provider_hint=" provider.is_ready=True",
        )


def test_require_approval_gate_triggered_fails_when_unknown_tool() -> None:
    with pytest.raises(AssertionError, match="never triggered desktop approval gate"):
        require_approval_gate_triggered(
            last_tool="web_search_tool",
            server_pending=0,
            ui_pending=False,
        )


def test_snapshot_loop_stuck_sec_tracks_snapshot_without_gate() -> None:
    assert (
        snapshot_loop_stuck_sec(
            last_tool="desktop_snapshot_tool",
            server_pending=0,
            ui_pending=False,
            loop_started_at=None,
        )
        == 0.0
    )
    started = 100.0
    assert (
        snapshot_loop_stuck_sec(
            last_tool="desktop_snapshot_tool",
            server_pending=0,
            ui_pending=False,
            loop_started_at=started,
            now=150.0,
        )
        == 50.0
    )
    assert (
        snapshot_loop_stuck_sec(
            last_tool="desktop_snapshot_tool",
            server_pending=1,
            ui_pending=False,
            loop_started_at=started,
            now=150.0,
        )
        is None
    )


def test_interact_without_gate_handoff_elapsed_requires_interact_seen() -> None:
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=None,
            server_pending=0,
            ui_pending=False,
            now=50.0,
            handoff_sec=10.0,
        )
        is False
    )


def test_interact_without_gate_handoff_elapsed_respects_pending_gate() -> None:
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=1,
            ui_pending=False,
            now=30.0,
            handoff_sec=10.0,
        )
        is False
    )
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=0,
            ui_pending=True,
            now=30.0,
            handoff_sec=10.0,
        )
        is False
    )


def test_interact_without_gate_handoff_elapsed_after_threshold() -> None:
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=0,
            ui_pending=False,
            now=19.9,
            handoff_sec=10.0,
        )
        is False
    )
    assert (
        interact_without_gate_handoff_elapsed(
            interact_seen_at=10.0,
            server_pending=0,
            ui_pending=False,
            now=20.0,
            handoff_sec=10.0,
        )
        is True
    )


def test_record_synthetic_dref_fallback_raises_when_budget_exceeded() -> None:
    budget = _DesktopFallbackBudget(synthetic_dref_limit=0, pending_seed_limit=1)
    with pytest.raises(AssertionError, match="synthetic dref fallback budget exceeded"):
        _record_synthetic_dref_fallback(budget, reason="unit-test")


def test_merge_desktop_progress_preserves_api_wall_timeout_err() -> None:
    merged = _merge_desktop_progress(
        {"active": False, "lastTool": "", "stepCount": 0},
        {
            "active": False,
            "lastTool": "",
            "stepCount": 0,
            "err": "api-progress-wall-timeout",
        },
    )
    assert merged.get("err") == "api-progress-wall-timeout"


def test_record_pending_seed_fallback_tracks_usage_within_budget() -> None:
    budget = _DesktopFallbackBudget(synthetic_dref_limit=1, pending_seed_limit=2)
    _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-1")
    _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-2")
    assert budget.pending_seed_used == 2


def test_record_pending_seed_fallback_raises_when_budget_exceeded() -> None:
    budget = _DesktopFallbackBudget(synthetic_dref_limit=1, pending_seed_limit=1)
    _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-1")
    with pytest.raises(AssertionError, match="pending seed fallback budget exceeded"):
        _record_pending_seed_fallback(budget, reason="unit-test", request_id="req-2")


def test_build_fallback_budget_uses_defaults_when_env_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE", raising=False)
    monkeypatch.delenv("MYRM_DESKTOP_E2E_MAX_SYNTHETIC_DREF_FALLBACKS", raising=False)
    monkeypatch.delenv("MYRM_DESKTOP_E2E_MAX_PENDING_SEED_FALLBACKS", raising=False)
    budget = _build_fallback_budget()
    assert budget.synthetic_dref_limit == 2
    assert budget.pending_seed_limit == 3


def test_build_fallback_budget_strict_mode_overrides_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYRM_DESKTOP_E2E_STRICT_FALLBACK_MODE", "1")
    monkeypatch.setenv("MYRM_DESKTOP_E2E_MAX_SYNTHETIC_DREF_FALLBACKS", "9")
    monkeypatch.setenv("MYRM_DESKTOP_E2E_MAX_PENDING_SEED_FALLBACKS", "9")
    budget = _build_fallback_budget()
    assert budget.synthetic_dref_limit == 0
    assert budget.pending_seed_limit == 0


@pytest.mark.asyncio
async def test_send_interact_nudge_raises_when_synthetic_dref_budget_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _baseline_markers(_: str) -> tuple[int, int]:
        return (0, 0)

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.activate_textedit_foreground",
        lambda: None,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.to_thread",
        _to_thread,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._nudge_baseline_markers",
        _baseline_markers,
    )
    budget = _DesktopFallbackBudget(synthetic_dref_limit=0, pending_seed_limit=1)
    with pytest.raises(AssertionError, match="synthetic dref fallback budget exceeded"):
        await _send_interact_nudge(
            chat=_DummyChat(),
            last_tool="desktop_vision_tool",
            fallback_budget=budget,
            chat_id="chat-1",
        )


@pytest.mark.asyncio
async def test_wait_desktop_tool_activity_raises_when_pending_seed_budget_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _sleep(_: float) -> None:
        return None

    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _probe(*_: object, **__: object) -> dict[str, object]:
        return {
            "active": False,
            "pending": False,
            "lastTool": "",
            "apiLastTool": "",
            "isStreaming": True,
            "completionStatus": "",
            "err": "api-progress-wall-timeout",
        }

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.probe_desktop_tool_progress",
        _probe,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.seed_pending_desktop_approval_for_test",
        lambda **_: "seed-1",
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.heartbeat_once",
        lambda: None,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.sleep",
        _sleep,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.to_thread",
        _to_thread,
    )

    async def _agent_stream_active_stub(*_: object, **__: object) -> bool:
        return False

    async def _resolve_server_pending_stub(**_: object) -> int:
        return 0

    async def _skip_completed_without_tools(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._agent_stream_active",
        _agent_stream_active_stub,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._resolve_server_pending",
        _resolve_server_pending_stub,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._fail_if_model_completed_without_desktop_tools",
        _skip_completed_without_tools,
    )
    budget = _DesktopFallbackBudget(synthetic_dref_limit=1, pending_seed_limit=0)
    with pytest.raises(AssertionError, match="pending seed fallback budget exceeded"):
        await _wait_desktop_tool_activity_failfast(
            chat=_DummyChat(),
            timeout_sec=30.0,
            fallback_budget=budget,
            chat_id="chat-1",
        )


@pytest.mark.asyncio
async def test_wait_desktop_tool_activity_raises_on_cumulative_api_timeout_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _sleep(_: float) -> None:
        return None

    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    calls = {"count": 0}

    async def _probe(*_: object, **__: object) -> dict[str, object]:
        calls["count"] += 1
        timeout_err = "api-progress-wall-timeout" if calls["count"] % 2 == 1 else ""
        return {
            "active": False,
            "pending": False,
            "lastTool": "",
            "apiLastTool": "",
            "isStreaming": True,
            "completionStatus": "",
            "err": timeout_err,
        }

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.probe_desktop_tool_progress",
        _probe,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.seed_pending_desktop_approval_for_test",
        lambda **_: "seed-1",
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.heartbeat_once",
        lambda: None,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.sleep",
        _sleep,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.to_thread",
        _to_thread,
    )

    async def _agent_stream_active_stub(*_: object, **__: object) -> bool:
        return False

    async def _resolve_server_pending_stub(**_: object) -> int:
        return 0

    async def _skip_completed_without_tools(*_: object, **__: object) -> None:
        return None

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._agent_stream_active",
        _agent_stream_active_stub,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._resolve_server_pending",
        _resolve_server_pending_stub,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._fail_if_model_completed_without_desktop_tools",
        _skip_completed_without_tools,
    )

    budget = _DesktopFallbackBudget(synthetic_dref_limit=1, pending_seed_limit=0)
    with pytest.raises(AssertionError, match="pending seed fallback budget exceeded"):
        await _wait_desktop_tool_activity_failfast(
            chat=_DummyChat(),
            timeout_sec=30.0,
            fallback_budget=budget,
            chat_id="chat-1",
        )


@pytest.mark.asyncio
async def test_ensure_nudge_chat_surface_guarded_returns_false_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _wait_for_timeout(*_: object, **__: object) -> object:
        raise asyncio.TimeoutError()

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.wait_for",
        _wait_for_timeout,
    )
    ok = await _ensure_nudge_chat_surface_guarded(
        _DummyChat(),
        chat_id="chat-timeout",
        timeout_sec=1.0,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_wait_nudge_send_surface_returns_false_when_surface_guard_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _surface_guard_fail(*_: object, **__: object) -> bool:
        return False

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._ensure_nudge_chat_surface_guarded",
        _surface_guard_fail,
    )
    chat = _SurfaceProbeChat()
    ok = await _wait_nudge_send_surface(chat, chat_id="chat-1", timeout_sec=10.0)
    assert ok is False
    assert chat.calls == []


@pytest.mark.asyncio
async def test_wait_nudge_send_surface_returns_false_on_send_button_wait_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _surface_guard_ok(*_: object, **__: object) -> bool:
        return True

    async def _wait_for_timeout(*_: object, **__: object) -> object:
        raise asyncio.TimeoutError()

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._ensure_nudge_chat_surface_guarded",
        _surface_guard_ok,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.wait_for",
        _wait_for_timeout,
    )
    chat = _SurfaceProbeChat()
    ok = await _wait_nudge_send_surface(chat, chat_id="chat-timeout", timeout_sec=8.0)
    assert ok is False
    assert chat.calls == ["ensure_react_e2e_bridge"]


@pytest.mark.asyncio
async def test_send_interact_nudge_seeds_pending_when_follow_up_recover_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _baseline_markers(_: str) -> tuple[int, int]:
        return (0, 0)

    async def _stream_inactive(*_: object, **__: object) -> bool:
        return False

    async def _send_surface_ready(*_: object, **__: object) -> bool:
        return True

    async def _surface_recover_fail(*_: object, **__: object) -> bool:
        return False

    async def _abort_stream(*_: object, **__: object) -> None:
        return None

    async def _wait_stream_idle_ok(*_: object, **__: object) -> bool:
        return True

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.activate_textedit_foreground",
        lambda: None,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.to_thread",
        _to_thread,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._nudge_baseline_markers",
        _baseline_markers,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._agent_stream_active",
        _stream_inactive,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._wait_nudge_send_surface",
        _send_surface_ready,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._ensure_nudge_chat_surface_guarded",
        _surface_recover_fail,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._abort_stuck_ui_stream",
        _abort_stream,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._wait_stream_idle",
        _wait_stream_idle_ok,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.seed_pending_desktop_approval_for_test",
        lambda **_: "req-seed-1",
    )
    budget = _DesktopFallbackBudget(synthetic_dref_limit=2, pending_seed_limit=2)
    chat = _NudgeRetryChat([RuntimeError("transport closed")])
    await _send_interact_nudge(
        chat=chat,  # type: ignore[arg-type]
        last_tool="desktop_vision_tool",
        fallback_budget=budget,
        chat_id="chat-1",
    )
    assert chat.submit_calls == 1
    assert budget.pending_seed_used == 1


@pytest.mark.asyncio
async def test_send_interact_nudge_follow_up_resend_retries_once_with_recover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _to_thread(func: object, *args: object, **kwargs: object) -> object:
        return func(*args, **kwargs)  # type: ignore[misc]

    async def _stream_inactive(*_: object, **__: object) -> bool:
        return False

    async def _send_surface_ready(*_: object, **__: object) -> bool:
        return True

    async def _surface_recover_ok(*_: object, **__: object) -> bool:
        return True

    async def _abort_stream(*_: object, **__: object) -> None:
        return None

    async def _wait_stream_idle_ok(*_: object, **__: object) -> bool:
        return True

    baseline_calls: list[str] = []

    async def _baseline_markers(_: str) -> tuple[int, int]:
        baseline_calls.append("baseline")
        return (0, 0)

    consumed_calls: list[int] = []

    async def _wait_consumed(
        *_: object,
        **__: object,
    ) -> bool:
        consumed_calls.append(1)
        return len(consumed_calls) >= 2

    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.activate_textedit_foreground",
        lambda: None,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe.asyncio.to_thread",
        _to_thread,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._nudge_baseline_markers",
        _baseline_markers,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._wait_nudge_consumed",
        _wait_consumed,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._agent_stream_active",
        _stream_inactive,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._wait_nudge_send_surface",
        _send_surface_ready,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._ensure_nudge_chat_surface_guarded",
        _surface_recover_ok,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._abort_stuck_ui_stream",
        _abort_stream,
    )
    monkeypatch.setattr(
        "tests.e2e.desktop_approval.gate_probe._wait_stream_idle",
        _wait_stream_idle_ok,
    )
    budget = _DesktopFallbackBudget(synthetic_dref_limit=2, pending_seed_limit=2)
    chat = _NudgeRetryChat(
        [
            {"submit": {"debug": {"turn": {"userCount": 0}}}},
            RuntimeError("transport closed"),
            {"submit": {"debug": {"turn": {"userCount": 1}}}},
        ]
    )
    await _send_interact_nudge(
        chat=chat,  # type: ignore[arg-type]
        last_tool="desktop_vision_tool",
        fallback_budget=budget,
        chat_id="chat-1",
    )
    assert chat.submit_calls == 3
    assert len(consumed_calls) >= 2
