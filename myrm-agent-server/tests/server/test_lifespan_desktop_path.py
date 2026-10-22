"""Wiring tests: the lifespan hydrates the desktop PATH and consumes a pending Python environment reset before any
other startup work, and a reset that cannot be carried out never keeps the server from starting."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.server import lifespan as lifespan_module


class _StopStartup(Exception):
    """Raised by the step right after hydration so the test never boots the real server."""


@pytest.mark.asyncio
async def test_lifespan_hydrates_path_before_tls_and_subsystem_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _hydrate() -> list[str]:
        calls.append("hydrate")
        return []

    def _next_step() -> bool:
        calls.append("next")
        raise _StopStartup

    monkeypatch.setattr("app.startup.desktop_path.hydrate_desktop_path", _hydrate)
    monkeypatch.setattr("myrm_agent_harness.infra.tls_compat.apply_global_tls_relaxation", _next_step)

    with pytest.raises(_StopStartup):
        async with lifespan_module.optimized_lifespan(FastAPI()):
            pass

    assert calls == ["hydrate", "next"]


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
    monkeypatch.setattr(lifespan_module, "_phase_1a_sequential", _first_phase)

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
    monkeypatch.setattr(lifespan_module, "_phase_1a_sequential", _first_phase)

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
    monkeypatch.setattr(lifespan_module, "_phase_1a_sequential", _first_phase)

    with caplog.at_level("WARNING", logger=lifespan_module.logger.name), pytest.raises(_StopStartup):
        async with lifespan_module.optimized_lifespan(FastAPI()):
            pass

    assert calls == ["reset", "phase-1a"]
    assert "Python environment reset skipped: volume is read-only" in caplog.text
