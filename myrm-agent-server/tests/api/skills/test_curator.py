from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus, SkillUsageStats


def test_curator_config_consolidation_default_false(client: TestClient, tmp_path: Path) -> None:
    """Fresh curator config must have consolidation_enabled=false."""
    import app.core.skills.curator_service as curator_service

    curator_service._curator_config = None
    with patch.object(curator_service, "_get_data_dir", return_value=tmp_path):
        response = client.get("/api/v1/skills/curator/config")
    assert response.status_code == 200
    assert response.json()["consolidation_enabled"] is False


def test_curator_config_get(client: TestClient):
    response = client.get("/api/v1/skills/curator/config")
    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert "interval_hours" in data
    assert "stale_after_days" in data
    assert "archive_after_days" in data


def test_curator_config_update(client: TestClient):
    response = client.patch("/api/v1/skills/curator/config", json={"enabled": False, "interval_hours": 24})
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["interval_hours"] == 24

    response = client.patch("/api/v1/skills/curator/config", json={"enabled": True, "interval_hours": 168})
    assert response.status_code == 200


def test_curator_config_includes_consolidation_fields(client: TestClient):
    """Consolidation fields should be present in config response."""
    response = client.get("/api/v1/skills/curator/config")
    assert response.status_code == 200
    data = response.json()
    assert "consolidation_enabled" in data
    assert "consolidation_min_cluster_size" in data
    assert "consolidation_similarity_threshold" in data


def test_curator_config_update_consolidation(client: TestClient):
    """Consolidation config should be updatable."""
    response = client.patch(
        "/api/v1/skills/curator/config",
        json={
            "consolidation_enabled": True,
            "consolidation_min_cluster_size": 4,
            "consolidation_similarity_threshold": 0.8,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["consolidation_enabled"] is True
    assert data["consolidation_min_cluster_size"] == 4
    assert data["consolidation_similarity_threshold"] == 0.8


def test_curator_run(client: TestClient):
    response = client.post("/api/v1/skills/curator/run")
    assert response.status_code == 200
    data = response.json()
    assert "skills_scanned" in data
    assert "total_transitions" in data
    assert "stale_count" in data


def test_curator_history(client: TestClient):
    response = client.get("/api/v1/skills/curator/history")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


# ── Lifecycle action tests (mocked backend) ────────────────────────────


def _mock_resolve(name: str) -> Path:
    return Path(f"/tmp/mock_skills/{name}")


class _MockCollector:
    """Minimal mock for SkillStatsCollector used in lifecycle tests."""

    def __init__(self, stats: SkillUsageStats) -> None:
        self._stats = stats
        self.last_lifecycle_update: tuple[Path, str] | None = None
        self.last_pinned_update: tuple[Path, bool] | None = None

    def get_stats(self, skill_path: Path) -> SkillUsageStats:
        return self._stats

    def update_lifecycle_status(self, skill_path: Path, status: str) -> None:
        self._stats.lifecycle_status = status
        self.last_lifecycle_update = (skill_path, status)

    def set_pinned(self, skill_path: Path, *, pinned: bool) -> None:
        self._stats.pinned = pinned
        self.last_pinned_update = (skill_path, pinned)


def test_archive_pinned_skill_returns_409(client: TestClient):
    """Archiving a pinned skill must be rejected with 409."""
    stats = SkillUsageStats(pinned=True, lifecycle_status=SkillLifecycleStatus.ACTIVE)
    mock_collector = _MockCollector(stats)

    with (
        patch("app.api.skills.curator._resolve_skill_path", side_effect=_mock_resolve),
        patch("app.api.skills.curator._get_stats_collector", return_value=mock_collector),
    ):
        response = client.patch(
            "/api/v1/skills/curator/test_skill/lifecycle",
            json={"action": "archive"},
        )
    assert response.status_code == 409
    assert "pinned" in response.json()["detail"].lower()
    assert mock_collector.last_lifecycle_update is None


def test_archive_unpinned_skill_succeeds(client: TestClient):
    """Archiving an unpinned skill should succeed normally."""
    stats = SkillUsageStats(pinned=False, lifecycle_status=SkillLifecycleStatus.ACTIVE)
    mock_collector = _MockCollector(stats)

    with (
        patch("app.api.skills.curator._resolve_skill_path", side_effect=_mock_resolve),
        patch("app.api.skills.curator._get_stats_collector", return_value=mock_collector),
    ):
        response = client.patch(
            "/api/v1/skills/curator/test_skill/lifecycle",
            json={"action": "archive"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "archive"
    assert data["new_status"] == "archived"
    assert mock_collector.last_lifecycle_update is not None


def test_pin_unpin_lifecycle(client: TestClient):
    """Pin and unpin operations should toggle pinned state."""
    stats = SkillUsageStats(pinned=False, lifecycle_status=SkillLifecycleStatus.ACTIVE)
    mock_collector = _MockCollector(stats)

    with (
        patch("app.api.skills.curator._resolve_skill_path", side_effect=_mock_resolve),
        patch("app.api.skills.curator._get_stats_collector", return_value=mock_collector),
    ):
        response = client.patch(
            "/api/v1/skills/curator/test_skill/lifecycle",
            json={"action": "pin"},
        )
    assert response.status_code == 200
    assert response.json()["pinned"] is True

    with (
        patch("app.api.skills.curator._resolve_skill_path", side_effect=_mock_resolve),
        patch("app.api.skills.curator._get_stats_collector", return_value=mock_collector),
    ):
        response = client.patch(
            "/api/v1/skills/curator/test_skill/lifecycle",
            json={"action": "unpin"},
        )
    assert response.status_code == 200
    assert response.json()["pinned"] is False


def test_restore_archived_skill(client: TestClient):
    """Restore should transition an archived skill back to active."""
    stats = SkillUsageStats(pinned=False, lifecycle_status=SkillLifecycleStatus.ARCHIVED)
    mock_collector = _MockCollector(stats)

    with (
        patch("app.api.skills.curator._resolve_skill_path", side_effect=_mock_resolve),
        patch("app.api.skills.curator._get_stats_collector", return_value=mock_collector),
    ):
        response = client.patch(
            "/api/v1/skills/curator/test_skill/lifecycle",
            json={"action": "restore"},
        )
    assert response.status_code == 200
    assert response.json()["new_status"] == "active"


# ── Consolidation endpoint tests (mocked service) ────────────────────────


def test_consolidation_preview_empty(client: TestClient):
    """Preview should return empty plan when no skills exist."""
    from myrm_agent_harness.agent.skills.curator.consolidation.types import ConsolidationPlan

    async def mock_preview():
        return ConsolidationPlan()

    with patch("app.core.skills.curator_service.run_consolidation_preview", side_effect=mock_preview):
        response = client.post("/api/v1/skills/curator/consolidation/preview")
    assert response.status_code == 200
    data = response.json()
    assert data["actions"] == []
    assert data["total_skills_affected"] == 0
    assert data["estimated_reduction"] == 0


def test_consolidation_preview_with_actions(client: TestClient):
    """Preview should return plan with actions when clusters exist."""
    from myrm_agent_harness.agent.skills.curator.consolidation.types import (
        ConsolidationAction,
        ConsolidationActionType,
        ConsolidationPlan,
    )

    plan = ConsolidationPlan(
        actions=[
            ConsolidationAction(
                action_type=ConsolidationActionType.MERGE,
                target_skill="git_operations_skill",
                source_skills=("git_commit_skill", "git_push_skill"),
                reasoning="Related git operations",
            ),
        ],
        total_skills_affected=2,
        estimated_reduction=1,
        preview_summary="• Merge 2 skills into 'git_operations_skill'",
    )

    async def mock_preview():
        return plan

    with patch("app.core.skills.curator_service.run_consolidation_preview", side_effect=mock_preview):
        response = client.post("/api/v1/skills/curator/consolidation/preview")
    assert response.status_code == 200
    data = response.json()
    assert len(data["actions"]) == 1
    assert data["actions"][0]["action_type"] == "merge"
    assert data["actions"][0]["target_skill"] == "git_operations_skill"
    assert data["total_skills_affected"] == 2
    assert data["estimated_reduction"] == 1


def test_consolidation_execute_empty(client: TestClient):
    """Execute should return empty result when nothing to consolidate."""

    async def mock_execute():
        return {
            "success_count": 0,
            "failure_count": 0,
            "total_archived": 0,
            "total_created": 0,
            "net_reduction": 0,
            "summary": "No skills available for consolidation.",
            "agent_refs_updated": 0,
        }

    with patch("app.core.skills.curator_service.run_consolidation_execute", side_effect=mock_execute):
        response = client.post("/api/v1/skills/curator/consolidation/execute")
    assert response.status_code == 200
    data = response.json()
    assert data["success_count"] == 0
    assert data["agent_refs_updated"] == 0


def test_consolidation_execute_with_results(client: TestClient):
    """Execute should return results when consolidation is performed."""

    async def mock_execute():
        return {
            "success_count": 2,
            "failure_count": 0,
            "total_archived": 4,
            "total_created": 1,
            "net_reduction": 3,
            "summary": "Consolidated 4 skills into 2 umbrellas.",
            "agent_refs_updated": 1,
        }

    with patch("app.core.skills.curator_service.run_consolidation_execute", side_effect=mock_execute):
        response = client.post("/api/v1/skills/curator/consolidation/execute")
    assert response.status_code == 200
    data = response.json()
    assert data["success_count"] == 2
    assert data["total_archived"] == 4
    assert data["net_reduction"] == 3
    assert data["agent_refs_updated"] == 1
