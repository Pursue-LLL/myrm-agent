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
            json={
                "url": "https://github.com/nonexistent-owner-xyz/nonexistent-repo-abc"
            },
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

    def test_search_and_install_agent_plugin_discovery_e2e(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """E2E test verifying Agent Plugin discovery search and installation response schemas."""
        from unittest.mock import AsyncMock
        from myrm_agent_harness.agent.skills.market.service import EnrichedSearchResult
        from myrm_agent_harness.backends.skills.market_protocols import SkillInstallResult, SkillSearchResult

        plugin_search_res = EnrichedSearchResult(
            result=SkillSearchResult(
                id="plugin::code-review-plugin",
                name="code-review-plugin",
                description="Agent plugin for comprehensive code reviews",
                source="github",
                author="myrm",
                install_url="https://github.com/myrm/code-review-plugin.git",
                install_method="git",
                version="1.0.0",
                package_type="agent_plugin",
                keywords=["review", "linter", "git"],
            )
        )

        # 1. Test search returns package_type and keywords
        monkeypatch.setattr(
            "app.core.skills.marketplace.market_service.market_service.search",
            AsyncMock(return_value=[plugin_search_res]),
        )
        monkeypatch.setattr(
            "app.core.skills.marketplace.market_service.market_service.ensure_clawhub_registry",
            AsyncMock(),
        )

        res = client.get("/api/v1/skills/discovery/search?q=code-review")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        item = data["results"][0]
        assert item["name"] == "code-review-plugin"
        assert item["package_type"] == "agent_plugin"
        assert "review" in item["keywords"]

        # 2. Test install returns installed_skills
        install_res = SkillInstallResult(
            success=True,
            skill_name="code-review-plugin",
            skill_id="local::code-review-plugin",
            installed_path="/tmp/skills/code-review-plugin",
            installed_skills=["code-review", "git-lint"],
        )
        monkeypatch.setattr(
            "app.core.skills.marketplace.market_service.market_service.install",
            AsyncMock(return_value=install_res),
        )

        res_install = client.post(
            "/api/v1/skills/discovery/install",
            json={"skill_id": "plugin::code-review-plugin", "source": "github", "mount_to_agent": False},
        )
        assert res_install.status_code == 200
        install_data = res_install.json()
        assert install_data["success"] is True
        assert install_data["skill_name"] == "code-review-plugin"
        assert install_data["installed_skills"] == ["code-review", "git-lint"]

