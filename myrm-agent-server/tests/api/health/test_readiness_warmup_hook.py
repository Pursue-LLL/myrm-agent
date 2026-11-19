"""Readiness reporting the database ready is the signal that starts the background warm-up after the first screen.

[INPUT]
- app.api.health.router::readiness_check (POS: the readiness route the web UI gate polls)
- app.server.lifespan.background::start_warmup_after_first_screen (POS: brings the warm-up start forward)

[OUTPUT]
- Coverage that a ready database notifies the warm-up and a failing one does not

[POS]
Health API tests. The UI gate opens on ``checks.database``; the warm-up must not compete with the first screen's requests,
so it starts a settle delay after the first such response.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.api.health import router as health_router
from app.server.lifespan import background


class _Session:
    def __init__(self, *, database_up: bool) -> None:
        self._database_up = database_up

    async def execute(self, _statement: object) -> None:
        if not self._database_up:
            raise RuntimeError("database unavailable")


def _install_fakes(monkeypatch: pytest.MonkeyPatch, *, database_up: bool) -> list[str]:
    """Stub the three dependency checks (no store is opened) and record the warm-up notifications."""

    @asynccontextmanager
    async def session() -> AsyncIterator[_Session]:
        yield _Session(database_up=database_up)

    async def vector_store() -> object:
        return object()

    notified: list[str] = []
    monkeypatch.setattr(health_router, "get_session", session)
    monkeypatch.setattr("app.core.retriever.vector.defaults.create_default_vector_store", vector_store)
    monkeypatch.setattr("app.core.retriever.get_graph_store", lambda memory_enabled: None)
    monkeypatch.setattr(background, "start_warmup_after_first_screen", lambda: notified.append("notified"))
    return notified


async def test_a_ready_database_notifies_the_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    notified = _install_fakes(monkeypatch, database_up=True)

    body = await health_router.readiness_check()

    assert body["checks"] == {"database": True, "qdrant": True, "graph_db": True}
    assert notified == ["notified"]


async def test_a_failing_database_does_not_notify_the_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    notified = _install_fakes(monkeypatch, database_up=False)

    body = await health_router.readiness_check()

    checks = body["checks"]
    assert isinstance(checks, dict)
    assert body["ready"] is False
    assert checks["database"] is False
    assert notified == []
