"""[POS]: tests/api/memory/test_capacity_hitl_api.py
[INPUT]: None.
[OUTPUT]: Isolated integration tests for memory capacity inspection and HITL candidate remediation endpoints.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.capacity_hitl import router
from app.services.memory.capacity_hitl import CapacityHitlProvider


@pytest.fixture(autouse=True)
def setup_isolated_provider(tmp_path: Path):
    db_file = tmp_path / "test_capacity_hitl.db"
    CapacityHitlProvider.set_custom_db_path(db_file)
    yield
    CapacityHitlProvider.reset()


@pytest.mark.asyncio
async def test_capacity_hitl_workflow_end_to_end() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Check capacity status (880 / 1000 = 88% -> near_capacity)
        status_resp = await client.get(
            "/api/memory/capacity-hitl/status?total_entries=880&max_entries=1000"
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["capacity_ratio"] == 0.88
        assert status_data["alert_level"] == "near_capacity"

        # 2. Propose remediation candidates (read-only by default)
        entries_payload = [
            {
                "id": "e-coffee-1",
                "content": "用户每天早晨喜欢喝一杯冰美式咖啡",
                "tags": ["coffee"],
                "created_at": 1000.0,
                "access_count": 10,
            },
            {
                "id": "e-coffee-2",
                "content": "用户习惯在早晨喝一杯冰美式咖啡唤醒大脑",
                "tags": ["habit"],
                "created_at": 1010.0,
                "access_count": 8,
            },
            {
                "id": "e-stale-3",
                "content": "已废弃的测试网端口 9092 临时信息",
                "tags": ["obsolete"],
                "created_at": 500.0,
                "access_count": 0,
            },
        ]
        propose_resp = await client.post(
            "/api/memory/capacity-hitl/propose-candidates",
            json={"entries": entries_payload, "max_proposals": 5},
        )
        assert propose_resp.status_code == 200
        propose_data = propose_resp.json()
        assert propose_data["total_proposals"] >= 2
        proposals = propose_data["proposals"]

        merge_prop = next(p for p in proposals if p["action_kind"] == "merge")
        archive_prop = next(p for p in proposals if p["action_kind"] == "archive")
        assert merge_prop["status"] == "pending"
        assert archive_prop["status"] == "pending"
        arch_id = archive_prop["candidate_id"]

        # 3. List candidates
        list_resp = await client.get("/api/memory/capacity-hitl/candidates?status=pending")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 2

        # 4. Resolve candidate with CAS conflict check
        # 4.1 Simulate stale CAS hash mismatch
        tampered_hashes = {"e-stale-3": "tampered_hash_abc"}
        cas_fail_resp = await client.post(
            f"/api/memory/capacity-hitl/candidates/{arch_id}/resolve",
            json={
                "decision": "approved",
                "reviewer_note": "尝试批准",
                "current_entry_hashes": tampered_hashes,
            },
        )
        assert cas_fail_resp.status_code == 200
        fail_data = cas_fail_resp.json()
        assert fail_data["success"] is False
        assert "EXPIRED" in fail_data["message"]

        # 4.2 Resolve merge proposal successfully
        merge_id = merge_prop["candidate_id"]
        approve_resp = await client.post(
            f"/api/memory/capacity-hitl/candidates/{merge_id}/resolve",
            json={
                "decision": "approved",
                "reviewer_note": "人类审核确认合并去重",
            },
        )
        assert approve_resp.status_code == 200
        approve_data = approve_resp.json()
        assert approve_data["success"] is True
        assert approve_data["proposal"]["status"] == "approved"

        # 5. Verify query archived list
        arch_list_resp = await client.get("/api/memory/capacity-hitl/archived")
        assert arch_list_resp.status_code == 200
        assert "archived_entries" in arch_list_resp.json()
