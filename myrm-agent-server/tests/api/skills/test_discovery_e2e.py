import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.skills.discovery import router as discovery_router


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI(title="Skill Discovery Test App")
    test_app.include_router(discovery_router, prefix="/api/v1/skills")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


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

    def test_search_and_install_agent_plugin_discovery_e2e(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """E2E test verifying Agent Plugin discovery search and installation response schemas."""
        from unittest.mock import AsyncMock

        from myrm_agent_harness.agent.skills.market.service import EnrichedSearchResult
        from myrm_agent_harness.backends.skills.market_protocols import (
            SkillInstallResult,
            SkillSearchResult,
        )

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
            "app.api.skills.discovery.market_service.search",
            AsyncMock(return_value=[plugin_search_res]),
        )
        monkeypatch.setattr(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            AsyncMock(),
        )
        monkeypatch.setattr(
            "app.api.skills.discovery.market_service.get_installed_local_ids_by_name",
            AsyncMock(return_value={}),
        )

        res = client.get("/api/v1/skills/discovery/search?q=code-review")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        item = data["results"][0]
        assert item["name"] == "code-review-plugin"
        assert item["package_type"] == "agent_plugin"
        assert "review" in item["keywords"]

        # 2. Test search with package_type filter
        res_filtered = client.get("/api/v1/skills/discovery/search?q=code-review&package_type=skill")
        assert res_filtered.status_code == 200
        assert res_filtered.json()["total"] == 0

        res_plugin_filtered = client.get("/api/v1/skills/discovery/search?q=code-review&package_type=agent_plugin")
        assert res_plugin_filtered.status_code == 200
        assert res_plugin_filtered.json()["total"] == 1

        # 3. Test install returns installed_skills and declared_mcp_servers
        install_res = SkillInstallResult(
            success=True,
            skill_name="code-review-plugin",
            skill_id="local::code-review-plugin",
            installed_path="/tmp/skills/code-review-plugin",
            installed_skills=["code-review", "git-lint"],
            declared_mcp_servers=["sqlite-srv"],
        )
        monkeypatch.setattr(
            "app.api.skills.discovery.market_service.install",
            AsyncMock(return_value=install_res),
        )

        res_install = client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": "plugin::code-review-plugin",
                "source": "github",
                "mount_to_agent": False,
                "allow_downgrade": False,
            },
        )
        assert res_install.status_code == 200
        install_data = res_install.json()
        assert install_data["success"] is True
        assert install_data["skill_name"] == "code-review-plugin"
        assert install_data["installed_skills"] == ["code-review", "git-lint"]
        assert install_data["declared_mcp_servers"] == ["sqlite-srv"]

    def test_install_skill_downgrade_blocked_e2e(self, client: TestClient, monkeypatch: pytest.MonkeyPatch):
        """E2E test verifying skill downgrade blockage response."""
        from unittest.mock import AsyncMock

        from myrm_agent_harness.backends.skills.market_protocols import (
            SkillInstallResult,
        )

        downgrade_res = SkillInstallResult(
            success=False,
            skill_name="my-skill",
            error="Skill downgrade blocked: incoming version '1.0.0' is lower than installed version '1.2.0'.",
            error_code="DOWNGRADE_BLOCKED",
        )
        monkeypatch.setattr(
            "app.api.skills.discovery.market_service.install",
            AsyncMock(return_value=downgrade_res),
        )
        monkeypatch.setattr(
            "app.api.skills.discovery.market_service.ensure_clawhub_registry",
            AsyncMock(),
        )

        res = client.post(
            "/api/v1/skills/discovery/install",
            json={
                "skill_id": "github::test/my-skill",
                "source": "github",
                "allow_downgrade": False,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is False
        assert data["error_code"] == "DOWNGRADE_BLOCKED"
        assert "downgrade blocked" in data["error"]

    def test_uninstall_broadcasts_skill_pool_updated(self, client: TestClient, monkeypatch):
        """Test uninstalling a skill broadcasts SKILL_POOL_UPDATED event."""
        from unittest.mock import AsyncMock, MagicMock

        from myrm_agent_harness.backends.skills.market_protocols import (
            SkillInstallResult,
        )

        uninstall_res = SkillInstallResult(
            success=True,
            skill_name="code-review-plugin",
            skill_id="local::code-review-plugin",
            installed_skills=["code-review", "git-lint"],
        )
        monkeypatch.setattr(
            "app.api.skills.discovery.market_service.uninstall",
            AsyncMock(return_value=uninstall_res),
        )
        monkeypatch.setattr(
            "app.core.skills.store.service.skills_service.user_config.disable_local_skill",
            AsyncMock(),
        )

        mock_bus = MagicMock()
        monkeypatch.setattr("app.services.event.app_event_bus.get_event_bus", lambda: mock_bus)

        res = client.post(
            "/api/v1/skills/discovery/uninstall",
            json={"skill_id": "local::code-review-plugin", "force": True},
        )
        assert res.status_code == 200
        assert res.json()["success"] is True
        assert mock_bus.publish.called
        event = mock_bus.publish.call_args[0][0]
        assert event.event_type.value == "skill_pool_updated"
        assert event.data["action"] == "uninstall"
        assert event.data["skill_id"] == "local::code-review-plugin"
        assert event.data["uninstalled_skills"] == ["code-review", "git-lint"]
