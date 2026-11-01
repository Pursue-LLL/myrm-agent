"""Tests for KeyringGate: bounded execution of OS keyring calls."""

import threading
import time

from app.core.security.keyring_gate import KeyringGate

_TIMEOUT_SEC = 0.2
# Generous upper bound for "returned promptly"; the blocked fake waits far longer than this.
_PROMPT_SEC = 1.0
_STALL_SEC = 5.0


class _BlockingCall:
    """A keyring stand-in that waits for ``release`` like an unanswered authorization prompt."""

    def __init__(self, value: str | None) -> None:
        self.calls = 0
        self.release = threading.Event()
        self._value = value

    def __call__(self) -> str | None:
        self.calls += 1
        self.release.wait(_STALL_SEC)
        return self._value


def _wait_until(predicate, timeout_sec: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestFastCalls:
    def test_returns_value_without_calling_on_late(self) -> None:
        late: list[str] = []

        result = KeyringGate(_TIMEOUT_SEC).run(lambda: "secret", late.append)

        assert result == "secret"
        assert late == []

    def test_exception_is_swallowed_as_none(self) -> None:
        def boom() -> str | None:
            raise RuntimeError("keychain exploded")

        assert KeyringGate(_TIMEOUT_SEC).run(boom, lambda _value: None) is None

    def test_none_result_passes_through(self) -> None:
        assert KeyringGate(_TIMEOUT_SEC).run(lambda: None, lambda _value: None) is None

    def test_sequential_calls_each_run(self) -> None:
        gate = KeyringGate(_TIMEOUT_SEC)

        assert gate.run(lambda: "a", lambda _value: None) == "a"
        assert gate.run(lambda: "b", lambda _value: None) == "b"


class TestStalledCall:
    def test_caller_is_released_after_timeout(self) -> None:
        stalled = _BlockingCall("late-secret")
        gate = KeyringGate(_TIMEOUT_SEC)

        started = time.monotonic()
        result = gate.run(stalled, lambda _value: None)
        elapsed = time.monotonic() - started

        stalled.release.set()
        assert result is None
        assert _TIMEOUT_SEC <= elapsed < _PROMPT_SEC

    def test_later_calls_return_at_once_without_a_second_call(self) -> None:
        stalled = _BlockingCall("late-secret")
        gate = KeyringGate(_TIMEOUT_SEC)
        gate.run(stalled, lambda _value: None)

        started = time.monotonic()
        second = gate.run(lambda: "other", lambda _value: None)
        elapsed = time.monotonic() - started

        stalled.release.set()
        assert second is None
        assert elapsed < _TIMEOUT_SEC / 2
        assert stalled.calls == 1

    def test_late_value_is_delivered_and_gate_recovers(self) -> None:
        stalled = _BlockingCall("late-secret")
        late: list[str] = []
        gate = KeyringGate(_TIMEOUT_SEC)
        gate.run(stalled, late.append)

        stalled.release.set()

        assert _wait_until(lambda: late == ["late-secret"])
        assert gate.run(lambda: "fresh", late.append) == "fresh"

    def test_late_none_is_not_delivered_and_gate_recovers(self) -> None:
        stalled = _BlockingCall(None)
        late: list[str] = []
        gate = KeyringGate(_TIMEOUT_SEC)
        gate.run(stalled, late.append)

        stalled.release.set()

        assert _wait_until(lambda: gate.run(lambda: "fresh", late.append) == "fresh")
        assert late == []

    def test_worker_is_a_daemon_thread(self) -> None:
        stalled = _BlockingCall("late-secret")
        gate = KeyringGate(_TIMEOUT_SEC)
        gate.run(stalled, lambda _value: None)

        workers = [t for t in threading.enumerate() if t.name == "keyring-call"]
        stalled.release.set()

        assert workers
        assert all(t.daemon for t in workers)
