"""Unit tests: the API queue gate waits out a page's fan-out instead of letting a click queue behind it."""

from __future__ import annotations

from collections.abc import Callable

from tests.support import chrome_api_queue as gate

_API_URL = "http://127.0.0.1:18080"


class _Clock:
    """A clock that only moves when the code under test sleeps, so minutes of waiting cost no time."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _fast(**fields: object) -> dict[str, object]:
    return {"ok": True, "ms": 120, "complete": True, **fields}


def _wait(clock: _Clock, evaluate: Callable[[str], object], *, deadline_sec: float = 240.0) -> dict[str, object]:
    return gate.wait_for_api_queue_to_drain(
        evaluate, _API_URL, deadline_sec=deadline_sec, clock=clock.monotonic, sleep=clock.sleep
    )


def _scripted(clock: _Clock, probe_at: Callable[[float, int], object]) -> Callable[[str], object]:
    """A page whose n-th probe, run at the clock's current time, answers ``probe_at(time, n)``."""
    calls = {"n": 0}

    def evaluate(_js: str) -> object:
        calls["n"] += 1
        return probe_at(clock.now, calls["n"])

    return evaluate


def test_an_idle_page_passes_after_the_required_fast_probes() -> None:
    clock = _Clock()

    result = _wait(clock, _scripted(clock, lambda _t, _n: _fast()))

    assert result["outcome"] == "drained"
    assert result["probes"] == gate.FAST_PROBES_REQUIRED


def test_waits_while_probes_queue_behind_the_fan_out_then_passes() -> None:
    clock = _Clock()

    result = _wait(clock, _scripted(clock, lambda t, _n: _fast(ms=30_000) if t < 120.0 else _fast()))

    assert result["outcome"] == "drained"
    assert 120.0 <= clock.now <= 120.0 + gate.FAST_PROBES_REQUIRED * 1.0


def test_one_fast_sample_between_two_bursts_does_not_pass() -> None:
    clock = _Clock()

    result = _wait(clock, _scripted(clock, lambda _t, n: _fast() if n % 2 else _fast(ms=20_000)), deadline_sec=60.0)

    assert result["outcome"] == "deadline"


def test_a_page_that_is_still_loading_does_not_pass() -> None:
    clock = _Clock()

    result = _wait(clock, _scripted(clock, lambda t, _n: _fast(complete=t >= 30.0)))

    assert result["outcome"] == "drained"
    assert clock.now >= 30.0


def test_a_failed_probe_resets_the_streak() -> None:
    clock = _Clock()
    script = [_fast(), _fast(), {"ok": False, "ms": 50_000, "complete": True, "error": "TimeoutError"}, _fast(), _fast(), _fast()]

    result = _wait(clock, _scripted(clock, lambda _t, n: script[n - 1]))

    assert result["outcome"] == "drained"
    assert result["probes"] == len(script)


def test_a_page_that_cannot_be_evaluated_is_probed_again() -> None:
    clock = _Clock()
    attempts = {"n": 0}

    def evaluate(_js: str) -> object:
        attempts["n"] += 1
        if attempts["n"] <= 4:
            raise RuntimeError("Execution context was destroyed")
        return _fast()

    result = _wait(clock, evaluate)

    assert result["outcome"] == "drained"
    assert result["probes"] == 4 + gate.FAST_PROBES_REQUIRED


def test_a_result_that_is_not_a_probe_counts_as_a_failed_probe() -> None:
    clock = _Clock()

    result = _wait(clock, _scripted(clock, lambda _t, n: None if n <= 2 else _fast()))

    assert result["outcome"] == "drained"
    assert result["probes"] == 2 + gate.FAST_PROBES_REQUIRED


def test_gives_up_at_the_deadline_and_reports_the_last_probe() -> None:
    clock = _Clock()

    result = _wait(clock, _scripted(clock, lambda _t, _n: _fast(ms=45_000)), deadline_sec=90.0)

    assert result["outcome"] == "deadline"
    assert result["last"] == _fast(ms=45_000)
    assert clock.now >= 90.0


def test_probe_is_a_preflighted_get_toward_the_api_origin() -> None:
    js = gate.api_queue_probe_js(f"{_API_URL}/")

    assert f'"{_API_URL}"' in js
    assert "/api/v1/health/liveness" in js
    assert "'Content-Type': 'application/json'" in js
    assert "__API__" not in js
    assert "__ABORT_MS__" not in js
