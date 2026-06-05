import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
class TestDraftsE2E:
    """End-to-End integration test for Draft API Lifecycle."""

    @pytest.mark.asyncio
    async def test_draft_lifecycle(self, client: TestClient):
        # 1. Create a draft directly using ApprovalRegistry (simulating system.py handling the event)
        from app.services.approvals.registry import ApprovalRegistry

        record = await ApprovalRegistry.create_approval(
            agent_id="test_agent_123",
            chat_id="test_chat_123",
            action_type="skill_draft",
            payload={
                "skill_name": "test-extracted-skill",
                "description": "This is a test extracted skill",
                "content": '```markdown\n---\nname: test-extracted-skill\ndescription: "test"\n---\n\n# Rules\nTest rules\n```',
                "score": 0.95,
            },
            reason="Test draft",
        )

        draft_id = record.id

        # 2. Get unreviewed count
        resp = client.get("/api/v1/skills/drafts/unreviewed/count")
        assert resp.status_code == 200
        assert resp.json()["unreviewed_count"] >= 1

        # 3. Get the draft details
        resp = client.get(f"/api/v1/skills/drafts/{draft_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == draft_id
        assert data["status"] == "PENDING_REVIEW"
        assert "test-extracted-skill" in data["content"]

        # 4. Approve the draft
        resp = client.post(f"/api/v1/skills/drafts/{draft_id}/approve", json={"skill_name": "approved-test-skill"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "APPROVED"

        # 5. Create another draft to test reject (which triggers manager.add_knowledge)
        record2 = await ApprovalRegistry.create_approval(
            agent_id="test_agent_123",
            chat_id="test_chat_123",
            action_type="skill_draft",
            payload={
                "skill_name": "bad-skill",
                "description": "This is a bad skill to be rejected",
                "content": "Bad rules",
                "score": 0.1,
            },
            reason="Test reject",
        )
        draft_id_2 = record2.id

        # 6. Reject the draft
        resp = client.post(f"/api/v1/skills/drafts/{draft_id_2}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "REJECTED"

    @pytest.mark.asyncio
    async def test_seed_mock_draft_names_visible_in_list(self, client: TestClient):
        from app.services.approvals.registry import ApprovalRegistry

        for skill_name in ("test-frontend-approve", "test-frontend-reject"):
            await ApprovalRegistry.create_approval(
                agent_id="default",
                chat_id="test_chat_123",
                action_type="skill_draft",
                payload={
                    "skill_name": skill_name,
                    "description": f"E2E mock for {skill_name}",
                    "content": f"# {skill_name}",
                    "score": 0.95,
                },
                reason="Instinct Inbox E2E seed",
            )

        list_resp = client.get("/api/v1/skills/drafts?status=PENDING_REVIEW")
        assert list_resp.status_code == 200
        names = {d["name"] for d in list_resp.json()["drafts"]}
        assert "test-frontend-approve" in names
        assert "test-frontend-reject" in names

    def test_get_draft_not_found_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/skills/drafts/nonexistent-draft-id")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_double_approve_returns_400(self, client: TestClient) -> None:
        from app.services.approvals.registry import ApprovalRegistry

        record = await ApprovalRegistry.create_approval(
            agent_id="edge_agent",
            chat_id="edge_chat",
            action_type="skill_draft",
            payload={"skill_name": "double-approve", "content": "# x", "score": 0.5},
            reason="edge",
        )
        first = client.post(
            f"/api/v1/skills/drafts/{record.id}/approve",
            json={"skill_name": "double-approve-skill"},
        )
        assert first.status_code == 200
        second = client.post(
            f"/api/v1/skills/drafts/{record.id}/approve",
            json={"skill_name": "double-approve-skill"},
        )
        assert second.status_code == 400

    @pytest.mark.asyncio
    async def test_double_reject_returns_400(self, client: TestClient) -> None:
        from app.services.approvals.registry import ApprovalRegistry

        record = await ApprovalRegistry.create_approval(
            agent_id="edge_agent",
            chat_id="edge_chat",
            action_type="skill_draft",
            payload={"skill_name": "double-reject", "content": "# x", "score": 0.5},
            reason="edge",
        )
        first = client.post(f"/api/v1/skills/drafts/{record.id}/reject")
        assert first.status_code == 200
        second = client.post(f"/api/v1/skills/drafts/{record.id}/reject")
        assert second.status_code == 400

    def test_seed_mock_http_endpoint(self, client: TestClient) -> None:
        resp = client.post("/api/v1/skills/drafts/test/seed-mock")
        assert resp.status_code == 200
        body = resp.json()
        assert body["skill_names"] == ["test-frontend-approve", "test-frontend-reject"]
        assert len(body["created_ids"]) == 2
