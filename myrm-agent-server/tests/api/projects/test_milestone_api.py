"""
Tests for Milestone CRUD API endpoints.

[POS] Milestone management API integration tests. Validates CRUD operations,
status transitions, progress calculation, and roadmap summary through the HTTP layer.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="projects")

PREFIX = "/api/v1/projects"


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_project(client: httpx.AsyncClient, name: str = "Test Project") -> dict:
    resp = await client.post(f"{PREFIX}/", json={"name": name, "description": "A test project"})
    assert resp.status_code == 200, f"Got {resp.status_code}: {resp.text}"
    data = resp.json()
    return data["data"]["project"]


class TestMilestoneCRUD:
    """Milestone create/read/update/delete operations."""

    @pytest.mark.asyncio
    async def test_create_milestone(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client)
        resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones",
            json={"title": "Phase 1: Data Collection", "description": "Gather all data sources"},
        )
        assert resp.status_code == 200
        ms = resp.json()["data"]["milestone"]
        assert ms["title"] == "Phase 1: Data Collection"
        assert ms["status"] == "active"
        assert ms["projectId"] == project["id"]

    @pytest.mark.asyncio
    async def test_list_milestones(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "List Test")
        await async_client.post(f"{PREFIX}/{project['id']}/milestones", json={"title": "MS1"})
        await async_client.post(f"{PREFIX}/{project['id']}/milestones", json={"title": "MS2"})

        resp = await async_client.get(f"{PREFIX}/{project['id']}/milestones")
        assert resp.status_code == 200
        milestones = resp.json()["data"]["milestones"]
        assert len(milestones) == 2

    @pytest.mark.asyncio
    async def test_update_milestone(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "Update Test")
        create_resp = await async_client.post(f"{PREFIX}/{project['id']}/milestones", json={"title": "Original"})
        ms = create_resp.json()["data"]["milestone"]

        resp = await async_client.put(
            f"{PREFIX}/{project['id']}/milestones/{ms['id']}",
            json={"title": "Updated Title", "status": "completed"},
        )
        assert resp.status_code == 200
        updated = resp.json()["data"]["milestone"]
        assert updated["title"] == "Updated Title"
        assert updated["status"] == "completed"
        assert updated["completedAt"] is not None

    @pytest.mark.asyncio
    async def test_delete_milestone(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "Delete Test")
        create_resp = await async_client.post(f"{PREFIX}/{project['id']}/milestones", json={"title": "To Delete"})
        ms = create_resp.json()["data"]["milestone"]

        resp = await async_client.delete(f"{PREFIX}/{project['id']}/milestones/{ms['id']}")
        assert resp.status_code == 200

        list_resp = await async_client.get(f"{PREFIX}/{project['id']}/milestones")
        assert len(list_resp.json()["data"]["milestones"]) == 0

    @pytest.mark.asyncio
    async def test_get_roadmap_summary(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "Roadmap Test")
        await async_client.post(f"{PREFIX}/{project['id']}/milestones", json={"title": "Phase 1"})
        await async_client.post(f"{PREFIX}/{project['id']}/milestones", json={"title": "Phase 2"})

        resp = await async_client.get(f"{PREFIX}/{project['id']}/roadmap")
        assert resp.status_code == 200
        roadmap = resp.json()["data"]["roadmap"]
        assert roadmap["projectName"] == "Roadmap Test"
        assert len(roadmap["activeMilestones"]) == 2

    @pytest.mark.asyncio
    async def test_invalid_status_returns_error(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "Validation Test")
        create_resp = await async_client.post(f"{PREFIX}/{project['id']}/milestones", json={"title": "Test"})
        ms = create_resp.json()["data"]["milestone"]

        resp = await async_client.put(
            f"{PREFIX}/{project['id']}/milestones/{ms['id']}",
            json={"status": "invalid_status"},
        )
        assert resp.status_code == 422 or resp.status_code == 400

    @pytest.mark.asyncio
    async def test_project_description_and_goal_summary(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "Goal Test")
        resp = await async_client.put(
            f"{PREFIX}/{project['id']}",
            json={"description": "Competitive analysis project", "goal_summary": "Collecting Q3 data"},
        )
        assert resp.status_code == 200
        updated = resp.json()["data"]["project"]
        assert updated["description"] == "Competitive analysis project"
        assert updated["goalSummary"] == "Collecting Q3 data"
