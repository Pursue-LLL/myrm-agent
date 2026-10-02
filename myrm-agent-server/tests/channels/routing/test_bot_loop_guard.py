"""Unit tests for BotLoopGuard sliding-window bot-to-bot loop protection."""

from __future__ import annotations

from app.channels.routing.bot_loop_guard import BotLoopGuard


class _FakeClock:
    """Deterministic monotonic clock for window/cooldown timing assertions."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestBotLoopGuardAdmit:
    def test_under_threshold_all_ok(self) -> None:
        guard = BotLoopGuard(max_events=3, window_seconds=300.0, cooldown_seconds=600.0, clock=_FakeClock())
        assert guard.admit("tg:chat1") == (True, "ok")
        assert guard.admit("tg:chat1") == (True, "ok")
        assert guard.admit("tg:chat1") == (True, "ok")

    def test_trips_at_max_events(self) -> None:
        guard = BotLoopGuard(max_events=2, window_seconds=300.0, cooldown_seconds=600.0, clock=_FakeClock())
        assert guard.admit("c") == (True, "ok")
        assert guard.admit("c") == (True, "ok")
        assert guard.admit("c") == (False, "tripped")

    def test_cooldown_drops_until_expired_then_fresh_budget(self) -> None:
        clock = _FakeClock()
        guard = BotLoopGuard(max_events=1, window_seconds=300.0, cooldown_seconds=600.0, clock=clock)
        assert guard.admit("c") == (True, "ok")
        assert guard.admit("c") == (False, "tripped")
        clock.advance(599.9)
        assert guard.admit("c") == (False, "cooldown")
        clock.advance(0.1)
        # Window was cleared on trip, so cooldown expiry restores a fresh budget
        assert guard.admit("c") == (True, "ok")

    def test_window_slides_old_events_expire(self) -> None:
        clock = _FakeClock()
        guard = BotLoopGuard(max_events=2, window_seconds=300.0, cooldown_seconds=600.0, clock=clock)
        assert guard.admit("c") == (True, "ok")
        clock.advance(301.0)
        assert guard.admit("c") == (True, "ok")
        assert guard.admit("c") == (True, "ok")

    def test_conversations_isolated(self) -> None:
        guard = BotLoopGuard(max_events=1)
        assert guard.admit("chat-a") == (True, "ok")
        assert guard.admit("chat-b") == (True, "ok")
        assert guard.admit("chat-a") == (False, "tripped")
        assert guard.admit("chat-b") == (False, "tripped")

    def test_reset_clears_window_and_cooldown(self) -> None:
        guard = BotLoopGuard(max_events=1)
        guard.admit("c")
        guard.reset("c")
        assert guard.admit("c") == (True, "ok")


class TestBotLoopGuardMemory:
    def test_sweep_frees_idle_conversations(self) -> None:
        clock = _FakeClock()
        guard = BotLoopGuard(max_events=5, window_seconds=300.0, cooldown_seconds=600.0, clock=clock)
        guard.admit("idle-chat")
        assert guard.tracked_conversations == 1
        clock.advance(700.0)
        guard.admit("live-chat")  # triggers the periodic sweep
        assert guard.tracked_conversations == 1
        assert guard.admit("idle-chat") == (True, "ok")