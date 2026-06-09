import pytest
from fastapi.testclient import TestClient

from app.services.approvals.registry import ApprovalRegistry
from app.services.skills.growth_constants import is_background_growth_approval


class TestListPendingGrowthFilter:
    """GET /approvals excludes background growth drafts; keeps inline HITL."""

    @pytest.mark.asyncio
    async def test_list_pending_excludes_background_skill_draft(self, client: TestClient) -> None:
        record = await ApprovalRegistry.create_approval(
            agent_id="filter_test_agent",
            action_type="skill_draft",
            payload={"skill_name": "bg-draft", "content": "# x"},
            reason="background growth",
        )
        assert is_background_growth_approval(record.action_type, record.thread_id)

        resp = client.get("/api/v1/approvals?limit=100&offset=0")
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["approvals"]}
        assert record.id not in ids

    @pytest.mark.asyncio
    async def test_list_pending_includes_inline_skill_draft_with_thread_id(self, client: TestClient) -> None:
        record = await ApprovalRegistry.create_approval(
            agent_id="filter_test_agent",
            action_type="skill_draft",
            payload={"skill_name": "inline-draft", "content": "# x"},
            reason="inline HITL",
            thread_id="langgraph-thread-abc",
        )
        assert not is_background_growth_approval(record.action_type, record.thread_id)

        resp = client.get("/api/v1/approvals?limit=100&offset=0")
        assert resp.status_code == 200
        ids = {item["id"] for item in resp.json()["approvals"]}
        assert record.id in ids
