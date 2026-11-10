"""Wiring tests: the lifespan hydrates the desktop PATH beside phase 1a and finishes it before phase 1b, consumes a
pending Python environment reset before any other startup work, and a reset that cannot be carried out never keeps the
server from starting."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi import FastAPI

from app.server import lifespan as lifespan_module


class _StopStartup(Exception):
    """Raised by the phase a test stops at, so the test never boots the real server."""


@pytest.mark.asyncio
async def test_lifespan_finishes_path_hydration_before_phase_1b(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 1b is the first to spawn a child process or to check skill `requires.bins` against PATH."""
    calls: list[str] = []

    def _hydrate() -> list[str]:
        time.sleep(0.1)  # a slow login shell; runs in the executor thread
        calls.append("hydrate")
        return []

    async def _phase_1a() -> None:
        calls.append("phase-1a")

    async def _phase_1b() -> None:
        calls.append("phase-1b")
        raise _StopStartup

    monkeypatch.setattr("app.startup.desktop_path.hydrate_desktop_path", _hydrate)
    monkeypatch.setattr(lifespan_module.startup, "_phase_1a_sequential", _phase_1a)
    monkeypatch.setattr(lifespan_module.startup, "_phase_1b_parallel", _phase_1b)

    with pytest.raises(_StopStartup):
        async with lifespan_module.optimized_lifespan(FastAPI()):
            pass

    assert calls == ["phase-1a", "hydrate", "phase-1b"]


@pytest.mark.asyncio
async def test_lifespan_hydrates_path_beside_phase_1a(monkeypatch: pytest.MonkeyPatch) -> None:
    """Phase 1a (database, migrations) needs no PATH, so the login-shell probe must not hold it back."""
    calls: list[str] = []
    phase_1a_started = threading.Event()

    def _hydrate() -> list[str]:
        # Ends only once phase 1a has begun: hydration that ran before phase 1a would wait here for nothing.
        assert phase_1a_started.wait(timeout=5), "phase 1a never started while the PATH was being hydrated"
        calls.append("hydrate")
        return []

    async def _phase_1a() -> None:
        calls.append("phase-1a")
        phase_1a_started.set()

    async def _phase_1b() -> None:
        raise _StopStartup

    monkeypatch.setattr("app.startup.desktop_path.hydrate_desktop_path", _hydrate)
    monkeypatch.setattr(lifespan_module.startup, "_phase_1a_sequential", _phase_1a)
    monkeypatch.setattr(lifespan_module.startup, "_phase_1b_parallel", _phase_1b)

    with pytest.raises(_StopStartup):
        async with lifespan_module.optimized_lifespan(FastAPI()):
            pass

    assert calls == ["phase-1a", "hydrate"]


@pytest.mark.asyncio
async def test_lifespan_applies_a_pending_python_env_reset_before_any_startup_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    """The environment must be gone before a component can create or cache it, so no startup phase may precede the reset."""
    calls: list[str] = []

    def _apply_reset() -> bool:
        calls.append("reset")
        return True

    async def _first_phase() -> None:
        calls.append("phase-1a")
        raise _StopStartup

    monkeypatch.setattr("app.services.infra.python_env_reset.apply_pending_python_env_reset", _apply_reset)
    monkeypatch.setattr(lifespan_module.startup, "_phase_1a_sequential", _first_phase)

    with pytest.raises(_StopStartup):
        async with lifespan_module.optimized_lifespan(FastAPI()):
            pass

    assert calls == ["reset", "phase-1a"]


@pytest.mark.asyncio
async def test_lifespan_goes_straight_on_when_there_is_no_reset_to_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most starts carry no reset request: nothing removed must lead straight on to the startup phases."""
    calls: list[str] = []

    def _apply_reset() -> bool:
        calls.append("reset")
        return False

    async def _first_phase() -> None:
        calls.append("phase-1a")
        raise _StopStartup

    monkeypatch.setattr("app.services.infra.python_env_reset.apply_pending_python_env_reset", _apply_reset)
    monkeypatch.setattr(lifespan_module.startup, "_phase_1a_sequential", _first_phase)

    with pytest.raises(_StopStartup):
        async with lifespan_module.optimized_lifespan(FastAPI()):
            pass

    assert calls == ["reset", "phase-1a"]


@pytest.mark.asyncio
async def test_lifespan_still_starts_when_the_environment_reset_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A reset that cannot be carried out (for example a volume that refuses the removal) must not brick the sandbox."""
    calls: list[str] = []

    def _apply_reset() -> bool:
        calls.append("reset")
        raise PermissionError("volume is read-only")

    async def _first_phase() -> None:
        calls.append("phase-1a")
        raise _StopStartup

    monkeypatch.setattr("app.services.infra.python_env_reset.apply_pending_python_env_reset", _apply_reset)
    monkeypatch.setattr(lifespan_module.startup, "_phase_1a_sequential", _first_phase)

    with caplog.at_level("WARNING", logger=lifespan_module.logger.name), pytest.raises(_StopStartup):
        async with lifespan_module.optimized_lifespan(FastAPI()):
            pass

    assert calls == ["reset", "phase-1a"]
    assert "Python environment reset skipped: volume is read-only" in caplog.text
