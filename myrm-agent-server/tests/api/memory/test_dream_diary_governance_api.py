"""Integration tests for Dream Diary Governance and Auditable Provenance API endpoints.

[POS]
做梦日记治理与溯源 API 测试套件。端到端验证消息级溯源查询、条目锁定防遗忘、
人工事实纠偏、一键撤回彻底抹除，以及闲时与 REM 调度触发流程。

[INPUT]
- FastAPI TestClient / AsyncClient
- 模拟包含溯源引用的做梦碎片负载

[OUTPUT]
- 严格断言 REST 状态码、治理状态流转与双向溯源锚点完整性
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.dream_diary import router as dream_diary_router
from app.services.memory.dreaming import get_dream_diary_service


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting dream diary router for test suite."""
    api_app = FastAPI()
    api_app.include_router(dream_diary_router, prefix="/api")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset dream diary service before each test."""
    service = get_dream_diary_service()
    with service._lock:
        service._entries.clear()


@pytest.mark.asyncio
async def test_dream_diary_provenance_and_lifecycle_api(test_app: FastAPI) -> None:
    """Test full cycle: run dreaming -> retrieve provenance -> lock -> amend -> revoke."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Trigger dreaming with rich provenance
        payload = {
            "fragments": [
                {
                    "session_id": "sess_101",
                    "project_id": "proj_crm",
                    "chat_turn_count": 5,
                    "memories": [
                        {
                            "content": "Customer requires SAML 2.0 Single Sign-On for enterprise tier",
                            "confidence": 0.9,
                            "evidence": [
                                {
                                    "message_id": "msg_001",
                                    "speaker": "user",
                                    "verbatim_quote": "We strictly mandate SAML 2.0 SSO for enterprise",
                                }
                            ],
                        }
                    ],
                }
            ],
            "target_project_id": "proj_crm",
        }
        res_run = await client.post("/api/dream-diary/run", json=payload)
        assert res_run.status_code == 200
        run_data = res_run.json()
        assert run_data["status"] == "success"
        assert run_data["generated_count"] == 1
        entry_id = run_data["entries"][0]["entry_id"]

        # 2. Get entry provenance anchors
        res_prov = await client.get(f"/api/dream-diary/{entry_id}/provenance")
        assert res_prov.status_code == 200
        prov_data = res_prov.json()
        assert prov_data["status"] == "success"
        assert prov_data["entry_id"] == entry_id
        assert prov_data["anchors_count"] >= 1
        anchor = prov_data["provenance_anchors"][0]
        assert anchor["session_id"] == "sess_101"
        assert anchor["message_id"] == "msg_001"
        assert "SAML 2.0" in anchor["verbatim_quote"]
        assert len(anchor["hash_digest"]) == 16

        # 3. Lock entry permanently
        res_lock = await client.post(
            f"/api/dream-diary/{entry_id}/lock",
            json={"reason": "Approved enterprise security compliance requirement"},
        )
        assert res_lock.status_code == 200
        lock_data = res_lock.json()
        assert lock_data["entry"]["status"] == "locked"
        assert lock_data["entry"]["is_locked"] is True

        # Locked entry should reject regular feedback modification
        res_feedback = await client.post(
            f"/api/dream-diary/{entry_id}/feedback",
            json={"action": "reject", "reason": "Accidental rejection"},
        )
        assert res_feedback.status_code == 404

        # 4. Amend entry statement
        res_amend = await client.post(
            f"/api/dream-diary/{entry_id}/amend",
            json={
                "amended_statement": "Customer strictly requires SAML 2.0 and OIDC Single Sign-On",
                "amendment_notes": "Added OIDC per security review",
            },
        )
        assert res_amend.status_code == 200
        amend_data = res_amend.json()
        assert "OIDC" in amend_data["entry"]["amended_statement"]

        # 5. Revoke entry
        res_revoke = await client.post(
            f"/api/dream-diary/{entry_id}/revoke",
            params={"reason": "Customer downgraded to community edition"},
        )
        assert res_revoke.status_code == 200
        revoke_data = res_revoke.json()
        assert revoke_data["entry"]["status"] == "revoked"
        assert revoke_data["entry"]["is_locked"] is False


@pytest.mark.asyncio
async def test_dream_diary_scheduler_trigger_api(test_app: FastAPI) -> None:
    """Test triggering idle consolidation and REM backfill via scheduler endpoint."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "payload": {
                "reason": "rem_backfill",
                "target_project_id": "proj_analytics",
                "rem_lookback_days": 14,
            },
            "fragments_payload": [
                {
                    "session_id": "sess_rem_1",
                    "project_id": "proj_analytics",
                    "memories": [
                        {
                            "content": "Dashboard analytics charts must use UTC timezone",
                            "confidence": 0.88,
                            "evidence": ["Charts must render UTC timestamps"],
                        }
                    ],
                }
            ],
        }
        res = await client.post("/api/dream-diary/scheduler/trigger", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["reason"] == "rem_backfill"
        assert data["generated_count"] == 1
        assert "UTC timezone" in data["entries"][0]["cognitive_statement"]


@pytest.mark.asyncio
async def test_dream_diary_nonexistent_entry_404(test_app: FastAPI) -> None:
    """Test 404 responses for nonexistent entry operations."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_get = await client.get("/api/dream-diary/nonexistent_dream_id/provenance")
        assert res_get.status_code == 404

        res_lock = await client.post("/api/dream-diary/nonexistent_dream_id/lock", json={})
        assert res_lock.status_code == 404

        res_revoke = await client.post("/api/dream-diary/nonexistent_dream_id/revoke")
        assert res_revoke.status_code == 404

        res_amend = await client.post(
            "/api/dream-diary/nonexistent_dream_id/amend",
            json={"amended_statement": "Valid statement with enough characters"},
        )
        assert res_amend.status_code == 404
