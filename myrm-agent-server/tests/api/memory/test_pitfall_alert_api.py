"""Integration tests for proactive pitfall alert and decision assist API.

[POS]
Tests verifying shadow intent sniffing, causal triad matching, session muting,
and operational telemetry via FastAPI endpoints.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.pitfall_alert_router (router)
- app.services.memory.pitfall_alert.provider (PitfallAlertServiceProvider, get_pitfall_alert_service)

[OUTPUT]
- Test functions covering pitfall alert API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.pitfall_alert_router import router as pitfall_alert_router
from app.services.memory.pitfall_alert.provider import (
    PitfallAlertServiceProvider,
    get_pitfall_alert_service,
)


@pytest.fixture
def isolated_service() -> PitfallAlertServiceProvider:
    """Create an isolated provider instance for testing."""
    return PitfallAlertServiceProvider()


@pytest.fixture
def test_app(isolated_service: PitfallAlertServiceProvider) -> FastAPI:
    """Create a FastAPI test app with dependency override."""
    api_app = FastAPI()
    api_app.include_router(pitfall_alert_router, prefix="/api/memory")
    api_app.dependency_overrides[get_pitfall_alert_service] = lambda: isolated_service
    return api_app


@pytest.mark.asyncio
async def test_evaluate_casual_inquiry_silent(test_app: FastAPI) -> None:
    """Verify that casual inquiry queries do not trigger disruptive alerts."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/memory/pitfall-alert/evaluate",
            json={
                "user_input": "介绍一下 redis 的缓存淘汰策略有哪几种？",
                "session_id": "sess_inquiry",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_generated"] is False
        assert data["dispatched_channel"] == "silent"
        assert data["alert_card"] is None


@pytest.mark.asyncio
async def test_evaluate_commitment_triggers_alert_card(test_app: FastAPI) -> None:
    """Verify that architecture commitments match past failure postmortems and return alert cards."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/memory/pitfall-alert/evaluate",
            json={
                "user_input": "我们决定换成 redis 分布式锁来处理订单并发",
                "session_id": "sess_commit",
                "current_runtime_version": "Redis 7.2",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["alert_generated"] is True
        assert data["intent_detected"] is True
        assert data["triad_matched"] is True

        card = data["alert_card"]
        assert card is not None
        assert card["subject"].lower() == "redis"
        assert "死锁" in card["historical_pitfall"] or "雪崩" in card["historical_pitfall"]
        assert "Redlock" in card["recommended_action"] or "乐观锁" in card["recommended_action"]
        assert card["dispatch_channel"] in ("frontend_callout", "shadow_thought_only")


@pytest.mark.asyncio
async def test_session_mute_and_unmute_lifecycle(test_app: FastAPI) -> None:
    """Verify that muting a technical topic in a session silences alerts and unmuting restores them."""
    session_id = "sess_mute_test"
    eval_payload = {
        "user_input": "我们计划换成 redis 分布式锁作为主方案",
        "session_id": session_id,
    }

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. First evaluation triggers alert
        resp1 = await client.post("/api/memory/pitfall-alert/evaluate", json=eval_payload)
        assert resp1.status_code == 200
        assert resp1.json()["alert_generated"] is True

        # 2. Mute redis topic in this session
        mute_resp = await client.post(
            "/api/memory/pitfall-alert/mute",
            json={"session_id": session_id, "subject": "redis"},
        )
        assert mute_resp.status_code == 200
        assert mute_resp.json()["status"] == "muted"

        # 3. Subsequent evaluation is silent
        resp2 = await client.post("/api/memory/pitfall-alert/evaluate", json=eval_payload)
        assert resp2.status_code == 200
        assert resp2.json()["alert_generated"] is False
        assert resp2.json()["dispatched_channel"] == "silent"

        # 4. Unmute redis topic
        unmute_resp = await client.post(
            "/api/memory/pitfall-alert/unmute",
            json={"session_id": session_id, "subject": "redis"},
        )
        assert unmute_resp.status_code == 200
        assert unmute_resp.json()["status"] == "unmuted"

        # 5. Alert restored
        resp3 = await client.post("/api/memory/pitfall-alert/evaluate", json=eval_payload)
        assert resp3.status_code == 200
        assert resp3.json()["alert_generated"] is True


@pytest.mark.asyncio
async def test_seed_and_alert_custom_postmortem(test_app: FastAPI) -> None:
    """Verify registering a new causal triad immediately protects against corresponding decisions."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Seed custom postmortem
        seed_resp = await client.post(
            "/api/memory/pitfall-alert/seed",
            json={
                "subject": "sqlite",
                "approach": "多进程并发写 WAL 模式",
                "pitfall_lesson": "在高并发下发生 database is locked 死锁和崩溃事故",
                "validated_alternative": "引入连接池队列并限制单写者并发控制",
                "severity": "critical",
                "incident_date": "2025-08-10",
                "version_context": "SQLite 3.40",
            },
        )
        assert seed_resp.status_code == 201
        assert seed_resp.json()["status"] == "success"

        # Evaluate decision targeting the newly seeded topic
        eval_resp = await client.post(
            "/api/memory/pitfall-alert/evaluate",
            json={
                "user_input": "我们准备换成 sqlite 承担高并发持久化",
                "session_id": "sess_custom_seed",
            },
        )
        assert eval_resp.status_code == 200
        data = eval_resp.json()
        assert data["alert_generated"] is True
        assert data["alert_card"]["subject"] == "sqlite"
        assert "死锁" in data["alert_card"]["historical_pitfall"]


@pytest.mark.asyncio
async def test_status_endpoint(test_app: FastAPI) -> None:
    """Verify status endpoint returns operational counters."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/memory/pitfall-alert/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active"] is True
        assert data["seeded_triads_count"] >= 3
