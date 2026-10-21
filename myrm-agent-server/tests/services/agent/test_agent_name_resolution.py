"""Unit tests for deterministic agent name resolution."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import app.services.agent.agent_service as agent_service_module
from app.services.agent.agent_service import AgentService


class _FakeRepo:
    def __init__(self, profiles: list[SimpleNamespace]) -> None:
        self._profiles = profiles

    async def list_profiles(
        self,
        *,
        offset: int = 0,
        limit: int | None = None,
        exclude_ids: list[str] | None = None,
    ) -> list[SimpleNamespace]:
        del offset, limit, exclude_ids
        return self._profiles


class _FakeUow:
    def __init__(self, profiles: list[SimpleNamespace]) -> None:
        self.agent_repo = _FakeRepo(profiles)

    async def __aenter__(self) -> "_FakeUow":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> bool:
        del exc_type, exc, tb
        return False


@pytest.mark.asyncio
async def test_get_agents_by_name_returns_stable_sorted_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    profiles = [
        SimpleNamespace(id="c-user", display_name="My Agent", built_in=False),
        SimpleNamespace(id="a-user", display_name="my agent", built_in=False),
        SimpleNamespace(id="b-built-in", display_name="MY AGENT", built_in=True),
        SimpleNamespace(id="z-other", display_name="Other Agent", built_in=False),
    ]

    monkeypatch.setattr(agent_service_module, "UnitOfWork", lambda: _FakeUow(profiles))

    matches = await AgentService.get_agents_by_name("  My Agent  ")
    assert [m.id for m in matches] == ["a-user", "c-user", "b-built-in"]


@pytest.mark.asyncio
async def test_get_agents_by_name_ignores_blank_name(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def _uow_factory() -> _FakeUow:
        nonlocal called
        called = True
        return _FakeUow([])

    monkeypatch.setattr(agent_service_module, "UnitOfWork", _uow_factory)

    matches = await AgentService.get_agents_by_name("   ")
    assert matches == []
    assert called is False
