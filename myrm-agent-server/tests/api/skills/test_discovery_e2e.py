import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
class TestSkillDiscoveryE2E:
    """E2E tests for Skill Discovery API – analyze-url endpoint."""

    def test_analyze_url_valid_repo(self, client: TestClient):
        """Real GitHub repo returns valid schema (may find 0 skills)."""
        response = client.post(
            "/api/v1/skills/discovery/analyze-url",
            json={"url": "https://github.com/langchain-ai/langchain"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "urls" in data
        assert isinstance(data["urls"], list)

        for item in data["urls"]:
            assert "url" in item
            assert "name" in item
            assert "description" in item
            assert "is_installed" in item
            assert isinstance(item["is_installed"], bool)

    def test_analyze_url_nonexistent_repo(self, client: TestClient):
        """A nonexistent repo should return 200 with an empty or fallback list, not crash."""
        response = client.post(
            "/api/v1/skills/discovery/analyze-url",
            json={"url": "https://github.com/nonexistent-owner-xyz/nonexistent-repo-abc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["urls"], list)

    def test_analyze_url_deep_link(self, client: TestClient):
        """A deep-link (tree/branch/subdir) should be accepted."""
        response = client.post(
            "/api/v1/skills/discovery/analyze-url",
            json={"url": "https://github.com/langchain-ai/langchain/tree/master/libs"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["urls"], list)

    def test_analyze_url_empty_string(self, client: TestClient):
        """Empty URL should return 200 with empty urls (graceful degradation)."""
        response = client.post(
            "/api/v1/skills/discovery/analyze-url",
            json={"url": ""},
        )
        # Our service catches exceptions and returns empty list
        assert response.status_code in (200, 422)
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data["urls"], list)
            assert len(data["urls"]) == 0

    def test_analyze_url_shorthand(self, client: TestClient):
        """Shorthand 'owner/repo' should also work."""
        response = client.post(
            "/api/v1/skills/discovery/analyze-url",
            json={"url": "langchain-ai/langchain"},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["urls"], list)
