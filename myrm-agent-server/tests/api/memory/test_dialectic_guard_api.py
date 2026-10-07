# [POS]: tests/api/memory/test_dialectic_guard_api.py
# [INPUT]: app.api.memory.dialectic_guard_router, FastAPI app
# [OUTPUT]: Integration API tests for Dialectic Liveness Guard & Stale Pivot Discard (Item 116)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.dialectic_guard_router import (
    router as dialectic_guard_router,
)
from app.services.memory.dialectic_guard_service import (
    DialecticGuardService,
    get_dialectic_guard_service,
)


@pytest.fixture
def isolated_service() -> DialecticGuardService:
    """Provides an isolated DialecticGuardService instance."""
    return DialecticGuardService()


@pytest.fixture
def test_app(isolated_service: DialecticGuardService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(dialectic_guard_router, prefix="/api/memory")
    app.dependency_overrides[get_dialectic_guard_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_should_trigger_and_hung_thread_recovery_api(test_app: FastAPI) -> None:
    """Validate trigger conditions, token allocation, and hung thread recovery via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger first cycle at turn 5, t=10.0s
        res_t1 = await client.post(
            "/api/memory/dialectic-guard/should-trigger",
            json={"session_id": "sess_api_01", "current_turn": 5, "now_mono": 10.0},
        )
        assert res_t1.status_code == 200
        data_t1 = res_t1.json()
        assert data_t1["should_trigger"] is True
        assert data_t1["cycle_token"] == 1
        assert data_t1["effective_cadence"] == 5

        # 2. Duplicate trigger while running within timeout: rejected
        res_mid = await client.post(
            "/api/memory/dialectic-guard/should-trigger",
            json={"session_id": "sess_api_01", "current_turn": 6, "now_mono": 25.0},
        )
        assert res_mid.status_code == 200
        assert res_mid.json()["should_trigger"] is False

        # 3. Time elapsed past 2x timeout (30s * 2 = 60s -> at t=75s elapsed is 65s > 60s):
        # Dead slot recovered and new cycle token 2 allocated at turn 10
        res_t2 = await client.post(
            "/api/memory/dialectic-guard/should-trigger",
            json={"session_id": "sess_api_01", "current_turn": 10, "now_mono": 75.0},
        )
        assert res_t2.status_code == 200
        data_t2 = res_t2.json()
        assert data_t2["should_trigger"] is True
        assert data_t2["cycle_token"] == 2


@pytest.mark.asyncio
async def test_submit_result_and_orphan_rejection_api(test_app: FastAPI) -> None:
    """Validate submission acceptance and orphan zombie token rejection via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Launch cycle 1
        await client.post(
            "/api/memory/dialectic-guard/should-trigger",
            json={"session_id": "sess_api_02", "current_turn": 5, "now_mono": 10.0},
        )
        # Advance clock to recover hung slot and launch cycle 2
        await client.post(
            "/api/memory/dialectic-guard/should-trigger",
            json={"session_id": "sess_api_02", "current_turn": 10, "now_mono": 75.0},
        )

        # Zombie return with token 1: rejected
        res_orphan = await client.post(
            "/api/memory/dialectic-guard/submit-result",
            json={
                "session_id": "sess_api_02",
                "cycle_token": 1,
                "content": "Outdated zombie response",
                "now_mono": 80.0,
            },
        )
        assert res_orphan.status_code == 200
        assert res_orphan.json()["accepted"] is False

        # Current return with token 2: accepted and staged
        res_valid = await client.post(
            "/api/memory/dialectic-guard/submit-result",
            json={
                "session_id": "sess_api_02",
                "cycle_token": 2,
                "content": "Fresh authoritative dialectic insight",
                "now_mono": 82.0,
            },
        )
        assert res_valid.status_code == 200
        data_valid = res_valid.json()
        assert data_valid["accepted"] is True
        assert data_valid["staged"] is True


@pytest.mark.asyncio
async def test_consume_pending_and_stale_pivot_api(test_app: FastAPI) -> None:
    """Validate staged consumption and stale conversational pivot discard via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Trigger and submit at turn 5
        await client.post(
            "/api/memory/dialectic-guard/should-trigger",
            json={"session_id": "sess_api_03", "current_turn": 5, "now_mono": 10.0},
        )
        await client.post(
            "/api/memory/dialectic-guard/submit-result",
            json={
                "session_id": "sess_api_03",
                "cycle_token": 1,
                "content": "Consensus on database index optimization",
                "now_mono": 12.0,
            },
        )

        # Consume at turn 16: delta_turns = 16 - 5 = 11 > 10 (base 5 * 2) -> stale pivot discarded!
        res_consume = await client.post(
            "/api/memory/dialectic-guard/consume-pending",
            json={"session_id": "sess_api_03", "current_turn": 16},
        )
        assert res_consume.status_code == 200
        assert res_consume.json()["has_content"] is False
        assert res_consume.json()["content"] is None


@pytest.mark.asyncio
async def test_notify_mutation_and_telemetry_api(test_app: FastAPI) -> None:
    """Validate critical mutation wakeup signal, telemetry, and audits via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = "sess_api_04"
        # Trigger empty returns to step empty streak
        await client.post(
            "/api/memory/dialectic-guard/should-trigger",
            json={"session_id": session_id, "current_turn": 5, "now_mono": 10.0},
        )
        await client.post(
            "/api/memory/dialectic-guard/submit-result",
            json={"session_id": session_id, "cycle_token": 1, "content": ""},
        )

        # Telemetry check shows streak 1, cadence = 10
        res_tel1 = await client.get(f"/api/memory/dialectic-guard/telemetry/{session_id}?current_turn=8")
        assert res_tel1.status_code == 200
        assert res_tel1.json()["empty_streak"] == 1
        assert res_tel1.json()["effective_cadence"] == 10

        # Notify mutation resets streak
        res_mut = await client.post(
            "/api/memory/dialectic-guard/notify-mutation",
            json={"session_id": session_id, "reason": "User pinned strict architecture rule"},
        )
        assert res_mut.status_code == 200
        assert res_mut.json()["effective_cadence"] == 5

        # Audits check confirms audit entries
        res_audits = await client.get(f"/api/memory/dialectic-guard/audits/{session_id}")
        assert res_audits.status_code == 200
        audits = res_audits.json()
        assert len(audits) >= 2
        assert any(a["action"] == "mutation_wakeup_streak_reset" for a in audits)
