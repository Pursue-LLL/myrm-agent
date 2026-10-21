"""Unit tests: the bridge wait leaves a page that is still loading alone instead of reloading it."""

from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from tests.support import chrome_bridge_load as load
from tests.support import chrome_mcp_e2e as support

_PAGE_URL = "http://127.0.0.1:3000/e2echat"


class _Clock:
    """A clock that only moves when the code under test sleeps, so minutes of waiting cost no time."""

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def __getattr__(self, name: str) -> object:
        return getattr(time, name)


def _probe(**fields: object) -> dict[str, object]:
    return {"ready": False, "readyState": "interactive", "scriptsDone": 0, "domScripts": 0, **fields}


def _settle(
    clock: _Clock,
    probe_at: Callable[[float], dict[str, object]],
    *,
    deadline: float = 600.0,
) -> tuple[str, int]:
    """Run the helper against a scripted page; returns the outcome and how many waits it made."""
    waits: list[float] = []
    outcome = load.wait_for_load_to_settle(
        lambda: probe_at(clock.now),
        probe_at(clock.now),
        deadline=deadline,
        on_wait=lambda: waits.append(clock.now),
        clock=clock.monotonic,
        sleep=clock.sleep,
    )
    return outcome, len(waits)


def test_returns_as_soon_as_the_bridge_appears() -> None:
    clock = _Clock()

    outcome, _ = _settle(clock, lambda t: _probe(ready=t >= 5.0, scriptsDone=int(t)))

    assert outcome == "ready"
    assert clock.now == 5.0


def test_keeps_waiting_while_scripts_keep_finishing_then_settles() -> None:
    clock = _Clock()

    def one_script_every_two_seconds(t: float) -> dict[str, object]:
        # 200s of progress is far beyond the stall window, so only progress can explain the wait.
        return _probe(readyState="complete" if t >= 200.0 else "interactive", scriptsDone=int(min(t, 200.0) // 2))

    outcome, waits = _settle(clock, one_script_every_two_seconds)

    assert outcome == "settled"
    assert 200.0 + load.SETTLE_SEC <= clock.now <= 200.0 + load.SETTLE_SEC + 2.0
    assert waits > 100


def test_a_stuck_load_is_reported_after_the_stall_window() -> None:
    clock = _Clock()

    outcome, _ = _settle(clock, lambda _t: _probe(scriptsDone=12, domScripts=30))

    assert outcome == "stalled"
    assert load.STALL_SEC <= clock.now <= load.STALL_SEC + 2.0


def test_a_complete_quiet_page_settles_after_the_quiet_period() -> None:
    clock = _Clock()

    outcome, _ = _settle(clock, lambda _t: _probe(readyState="complete", scriptsDone=90))

    assert outcome == "settled"
    assert clock.now == load.SETTLE_SEC


def test_stops_at_the_deadline_even_while_the_page_is_progressing() -> None:
    clock = _Clock()

    outcome, _ = _settle(clock, lambda t: _probe(scriptsDone=int(t)), deadline=90.0)

    assert outcome == "deadline"
    assert clock.now >= 90.0


def test_a_page_that_cannot_be_probed_is_left_to_the_heal_loop() -> None:
    clock = _Clock()

    def unobservable() -> dict[str, object]:
        raise RuntimeError("Execution context was destroyed")

    outcome = load.wait_for_load_to_settle(
        unobservable,
        _probe(),
        deadline=600.0,
        on_wait=lambda: None,
        clock=clock.monotonic,
        sleep=clock.sleep,
    )

    assert outcome == "unobservable"


def test_probe_reports_every_signal_the_wait_reads() -> None:
    for signal in ("readyState", "scriptsDone", "domScripts"):
        assert signal in support._REACT_E2E_BRIDGE_PROBE_JS
    # API polling must not look like loading: only finished script files count.
    assert r"\.js" in support._REACT_E2E_BRIDGE_PROBE_JS


class _BridgeWait:
    """``wait_for_react_e2e_bridge`` against a scripted page on a fake clock; records the heal reloads."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, probe_at: Callable[[float, int], dict[str, object]]) -> None:
        self.clock = _Clock()
        self.reload_times: list[float] = []
        self._probe_at = probe_at

        def evaluate(_page: object, js: str, **_: object) -> object:
            if js is support._REACT_E2E_BRIDGE_PROBE_JS:
                return self._probe_at(self.clock.now, len(self.reload_times))
            return True

        client = type("Client", (), {"evaluate": staticmethod(evaluate)})()
        self.client = client
        monkeypatch.setattr(support, "time", self.clock)
        monkeypatch.setattr(support, "touch_wall_progress", lambda **_: None)
        monkeypatch.setattr(support, "_react_bridge_wait_timeout_sec", lambda _t: 180.0)
        monkeypatch.setattr(support, "get_e2e_ui_url", lambda: "http://127.0.0.1:3000")
        monkeypatch.setattr(support, "_log_bridge_wait_state", lambda *_, **__: None)
        monkeypatch.setattr(support, "_bridge_failure_diagnostics", lambda *_: {})
        monkeypatch.setattr(support, "_trigger_attach_frontend_heal_once", lambda: None)
        monkeypatch.setattr(support, "_trigger_attach_client_warmup_once", lambda **_: None)
        monkeypatch.setattr(support, "dismiss_blocking_modals", lambda *_, **__: None)
        monkeypatch.setattr(support, "warm_ui_route", lambda *_, **__: None)
        monkeypatch.setattr(support, "reload_mcp_page", lambda *_, **__: self.reload_times.append(self.clock.now))

    def run(self) -> dict[str, object]:
        return support.wait_for_react_e2e_bridge(self.client, object(), timeout_sec=90.0, page_url=_PAGE_URL, require_attach=True)


def _rendered_shell(**fields: object) -> dict[str, object]:
    """The app shell is on screen but the E2E bridge has not been installed yet."""
    shell: dict[str, object] = {
        "hasAttach": False,
        "fallback": False,
        "hasInput": True,
        "hasAppLayout": True,
        "hasSkeleton": False,
        "bodyLength": 300,
        "href": _PAGE_URL,
    }
    return _probe(**{**shell, **fields})


def test_a_slow_hydrating_page_is_never_reloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure this guards: reloading at the first heal poll discards a hydration that needs ~100s."""

    def page(t: float, _reloads: int) -> dict[str, object]:
        if t >= 100.0:
            return _rendered_shell(ready=True, hasAttach=True, readyState="complete", scriptsDone=200)
        return _rendered_shell(scriptsDone=int(t // 2), domScripts=int(t // 2) + 5)

    wait = _BridgeWait(monkeypatch, page)

    result = wait.run()

    assert result["ready"] is True
    assert wait.reload_times == []
    assert wait.clock.now >= 100.0


def test_a_stuck_page_is_still_healed_by_a_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    def page(_t: float, reloads: int) -> dict[str, object]:
        if reloads:
            return _rendered_shell(ready=True, hasAttach=True, readyState="complete", scriptsDone=200)
        return _rendered_shell(scriptsDone=12, domScripts=30)

    wait = _BridgeWait(monkeypatch, page)

    result = wait.run()

    assert result["ready"] is True
    assert len(wait.reload_times) == 1
    assert wait.reload_times[0] >= load.STALL_SEC


def test_the_bridge_wait_still_fails_at_the_deadline_with_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    wait = _BridgeWait(monkeypatch, lambda t, _reloads: _rendered_shell(scriptsDone=int(t)))

    with pytest.raises(AssertionError, match="React E2E bridge did not become ready"):
        wait.run()

    assert wait.reload_times == []
    assert wait.clock.now >= 180.0


def test_a_trickling_skeleton_page_stalls_and_heals_before_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """When Turbopack trickles 1 chunk every 15s on an empty skeleton (12/107 in 180s), stall at 2*STALL_SEC and heal."""
    healed: list[float] = []

    def page(t: float, reloads: int) -> dict[str, object]:
        if reloads:
            return _rendered_shell(ready=True, hasAttach=True, readyState="complete", scriptsDone=107, domScripts=107)
        return _probe(
            hasAppLayout=False,
            hasSkeleton=True,
            bodyLength=0,
            scriptsDone=int(t // 15),
            domScripts=107,
        )

    wait = _BridgeWait(monkeypatch, page)
    monkeypatch.setattr(support, "_trigger_attach_frontend_heal_once", lambda: healed.append(wait.clock.now))

    result = wait.run()

    assert result["ready"] is True
    assert len(healed) == 1
    assert len(wait.reload_times) == 1
    assert wait.reload_times[0] == load.STALL_SEC * 2

