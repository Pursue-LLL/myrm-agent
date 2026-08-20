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
        seeded = [d for d in list_resp.json()["drafts"] if d.get("name") in ("test-frontend-approve", "test-frontend-reject")]
        assert len(seeded) == 2
        assert all(d["agent_id"] == agent_id for d in seeded)

    def test_seed_mock_namespace_isolates_drafts(self, client: TestClient) -> None:
        """Parallel SHARED runs must not deny each other's seeds (SSOT NAMESPACE_WRITE)."""
        agent_id = "builtin-general"
        resp_a = client.post(f"/api/v1/skills/drafts/test/seed-mock?agent_id={agent_id}&namespace=run-aaa")
        assert resp_a.status_code == 200
        body_a = resp_a.json()
        assert body_a["skill_names"] == [
            "test-frontend-approve-run-aaa",
            "test-frontend-reject-run-aaa",
        ]
        resp_b = client.post(f"/api/v1/skills/drafts/test/seed-mock?agent_id={agent_id}&namespace=run-bbb")
        assert resp_b.status_code == 200
        body_b = resp_b.json()
        assert body_b["skill_names"] == [
            "test-frontend-approve-run-bbb",
            "test-frontend-reject-run-bbb",
        ]

        list_resp = client.get("/api/v1/skills/drafts?status=PENDING_REVIEW")
        assert list_resp.status_code == 200
        drafts = list_resp.json()["drafts"]
        names = {d.get("name") for d in drafts}
        assert {
            "test-frontend-approve-run-aaa",
            "test-frontend-reject-run-aaa",
            "test-frontend-approve-run-bbb",
            "test-frontend-reject-run-bbb",
        }.issubset(names)

        # Re-seeding run-aaa must not deny run-bbb drafts.
        client.post(f"/api/v1/skills/drafts/test/seed-mock?agent_id={agent_id}&namespace=run-aaa")
        list_after = client.get("/api/v1/skills/drafts?status=PENDING_REVIEW")
        assert list_after.status_code == 200
        names_after = {d.get("name") for d in list_after.json()["drafts"]}
        assert "test-frontend-approve-run-bbb" in names_after
        assert "test-frontend-reject-run-bbb" in names_after
