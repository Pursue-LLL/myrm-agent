"""Tests for SteeringRegistry — session-level SteeringToken management."""

import threading

import pytest
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.services.agent.steering_registry import SteeringRegistry


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Ensure a clean registry for each test."""
    with SteeringRegistry._lock:
        SteeringRegistry._tokens.clear()


class TestSteeringRegistry:
    def test_register_and_has_active(self) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-1", token)
        assert SteeringRegistry.has_active("chat-1")

    def test_unregister(self) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-1", token)
        SteeringRegistry.unregister("chat-1")
        assert not SteeringRegistry.has_active("chat-1")

    def test_unregister_nonexistent_is_safe(self) -> None:
        SteeringRegistry.unregister("no-such-chat")

    def test_steer_queues_message(self) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-1", token)
        assert SteeringRegistry.steer("chat-1", "go left")
        assert token.has_pending

    def test_steer_returns_false_for_unknown_chat(self) -> None:
        assert not SteeringRegistry.steer("no-chat", "hello")

    def test_steer_message_reaches_token(self) -> None:
        token = SteeringToken()
        SteeringRegistry.register("chat-2", token)
        SteeringRegistry.steer("chat-2", "focus on testing")
        msgs = token.activate()
        assert msgs == ["focus on testing"]

    def test_concurrent_register_and_steer(self) -> None:
        """Multiple threads can safely register/steer/unregister concurrently."""
        results: list[bool] = []
        barrier = threading.Barrier(6)

        def worker(chat_id: str) -> None:
            barrier.wait()
            token = SteeringToken()
            SteeringRegistry.register(chat_id, token)
            ok = SteeringRegistry.steer(chat_id, f"msg-{chat_id}")
            results.append(ok)
            SteeringRegistry.unregister(chat_id)

        threads = [threading.Thread(target=worker, args=(f"c-{i}",)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results)
        assert len(results) == 6

    def test_register_overwrites_previous_token(self) -> None:
        old = SteeringToken()
        new = SteeringToken()
        SteeringRegistry.register("chat-3", old)
        SteeringRegistry.register("chat-3", new)
        SteeringRegistry.steer("chat-3", "hello")
        assert new.has_pending
        assert not old.has_pending

    def test_steer_unicode_and_special_chars(self) -> None:
        """Special chars, XSS payloads, emoji pass through unchanged."""
        token = SteeringToken()
        SteeringRegistry.register("chat-unicode", token)
        payload = "请用中文\n<script>alert('xss')</script>🚀 \x00\t"
        assert SteeringRegistry.steer("chat-unicode", payload)
        msgs = token.activate()
        assert msgs == [payload]

    def test_steer_very_long_message(self) -> None:
        """100KB message is accepted (validation is API-level)."""
        token = SteeringToken()
        SteeringRegistry.register("chat-long", token)
        long_msg = "A" * 100_000
        assert SteeringRegistry.steer("chat-long", long_msg)
        msgs = token.activate()
        assert msgs == [long_msg]

    def test_multiple_chats_isolated(self) -> None:
        """Steering one chat does not affect another."""
        t1, t2 = SteeringToken(), SteeringToken()
        SteeringRegistry.register("chat-a", t1)
        SteeringRegistry.register("chat-b", t2)
        SteeringRegistry.steer("chat-a", "for-a")
        assert t1.has_pending
        assert not t2.has_pending

    def test_lifecycle_register_steer_unregister(self) -> None:
        """Full lifecycle: register → steer → unregister → steer fails."""
        token = SteeringToken()
        SteeringRegistry.register("chat-lc", token)
        assert SteeringRegistry.steer("chat-lc", "msg1")
        SteeringRegistry.unregister("chat-lc")
        assert not SteeringRegistry.steer("chat-lc", "msg2")
        assert token.has_pending  # msg1 still in queue

    def test_rapid_steer_burst(self) -> None:
        """Rapid-fire steer calls all get queued correctly."""
        token = SteeringToken()
        SteeringRegistry.register("chat-burst", token)
        for i in range(100):
            assert SteeringRegistry.steer("chat-burst", f"burst-{i}")
        msgs = token.activate()
        assert len(msgs) == 100
        assert msgs[0] == "burst-0"
        assert msgs[99] == "burst-99"
