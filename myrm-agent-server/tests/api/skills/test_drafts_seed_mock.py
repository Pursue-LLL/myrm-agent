from fastapi.testclient import TestClient


class TestDraftsSeedMock:
    """HTTP tests for local-only Instinct Inbox seed-mock endpoint (no LLM)."""

    def test_seed_mock_http_endpoint(self, client: TestClient) -> None:
        resp = client.post("/api/v1/skills/drafts/test/seed-mock")
        assert resp.status_code == 200
        body = resp.json()
        assert body["skill_names"] == ["test-frontend-approve", "test-frontend-reject"]
        assert len(body["created_ids"]) == 2

    def test_seed_mock_http_endpoint_with_agent_id(self, client: TestClient) -> None:
        agent_id = "e2e-cloned-agent-abc"
        resp = client.post(f"/api/v1/skills/drafts/test/seed-mock?agent_id={agent_id}")
        assert resp.status_code == 200
        list_resp = client.get("/api/v1/skills/drafts?status=PENDING_REVIEW")
        assert list_resp.status_code == 200
        seeded = [
            d for d in list_resp.json()["drafts"]
            if d.get("name") in ("test-frontend-approve", "test-frontend-reject")
        ]
        assert len(seeded) == 2
        assert all(d["agent_id"] == agent_id for d in seeded)
