"""The risk-rule HTTP API has no ``action``: rules and hits are written and read without it, and an older client that still
sends one is not refused."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.risk import router as risk_api
from app.database.connection import get_db
from app.database.models import RiskHit
from app.services.risk.detection import RiskDetectionService

_RULE = {"rule_id": "mine", "display_name": "Mine", "pattern": "needle", "severity": "high"}


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.include_router(risk_api.router, prefix="/risk")

    async def database() -> AsyncIterator[AsyncSession]:
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    monkeypatch.setattr(risk_api, "_detection_service", RiskDetectionService())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://risk.test") as http:
        yield http


async def test_a_created_rule_is_read_back_without_an_action(client: AsyncClient) -> None:
    created = await client.post("/risk/rules", json=_RULE)
    fetched = await client.get("/risk/rules/mine")

    assert created.status_code == 200
    assert fetched.json()["data"] == created.json()["data"]
    assert "action" not in fetched.json()["data"]


async def test_a_client_that_still_sends_an_action_is_not_refused(client: AsyncClient) -> None:
    created = await client.post("/risk/rules", json={**_RULE, "action": "allow"})
    imported = await client.post("/risk/rules/batch-import", json={"rules": [{**_RULE, "rule_id": "other", "action": "block"}]})

    assert created.status_code == 200
    assert imported.json()["data"] == {"imported": 1, "skipped": []}


async def test_a_hit_is_listed_without_an_action(client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as db:
        db.add(RiskHit(trace_id="t", rule_id="mine", rule_name="Mine", severity="high", match_summary="chars:0-6"))
        await db.commit()

    hits = (await client.get("/risk/hits")).json()["data"]

    assert [(hit["rule_id"], hit["match_summary"]) for hit in hits["list"]] == [("mine", "chars:0-6")]
    assert "action" not in hits["list"][0]
