"""Wiring test: the lifespan hydrates the desktop PATH before any other startup work."""

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
