"""
Tests for Milestone CRUD API endpoints.

[POS] Milestone management API integration tests. Validates CRUD operations,
status transitions, progress calculation, and roadmap summary through the HTTP layer.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models.artifact import Artifact, ArtifactVersion
from app.database.models.assessment_import import AssessmentImportLedger
from app.database.models.kanban import KanbanBoardModel, KanbanTaskModel
from app.platform_utils.workspace_root import get_workspace_root
from app.services.kanban.service import KanbanService
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


async def _seed_artifact_with_markdown(markdown: str, *, chat_id: str | None = None) -> str:
    artifact_id = str(uuid4())
    version_id = str(uuid4())
    object_id = uuid4().hex
    vault = ArtifactVault(get_workspace_root())
    object_path = vault.get_object_path(object_id)
    object_path.parent.mkdir(parents=True, exist_ok=True)
    object_path.write_text(markdown, encoding="utf-8")

    async with get_session() as db:
        db.add(
            Artifact(
                id=artifact_id,
                name="Assessment Artifact",
                chat_id=chat_id,
                description="",
                is_deleted=False,
            )
        )
        db.add(
            ArtifactVersion(
                id=version_id,
                artifact_id=artifact_id,
                vault_uri=f"vault://{object_id}",
                sha256_hash="0" * 64,
                commit_message="seed",
            )
        )
        await db.commit()
    return artifact_id


def _error_issues_by_field(response: httpx.Response, field: str) -> list[str]:
    payload = response.json()
    if isinstance(payload, dict) and isinstance(payload.get("detail"), dict):
        payload = payload["detail"]
    details = payload.get("error", {}).get("details") or []
    issues: list[str] = []
    for item in details:
        if isinstance(item, dict) and item.get("field") == field:
            issue = item.get("issue")
            if isinstance(issue, str):
                issues.append(issue)
    return issues


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
    async def test_milestone_progress_counts_completed_status(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "Progress Status Test")
        create_resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones",
            json={"title": "Execution Phase"},
        )
        milestone = create_resp.json()["data"]["milestone"]

        board_id = "boardms001"
        async with get_session() as db:
            db.add(
                KanbanBoardModel(
                    id=board_id,
                    name="Project Board",
                    description="",
                    project_id=project["id"],
                    milestone_id=milestone["id"],
                )
            )
            db.add(
                KanbanTaskModel(
                    id="taskms001",
                    board_id=board_id,
                    title="Completed task",
                    description="",
                    status="completed",
                    priority="normal",
                )
            )
            db.add(
                KanbanTaskModel(
                    id="taskms002",
                    board_id=board_id,
                    title="Pending task",
                    description="",
                    status="ready",
                    priority="normal",
                )
            )
            await db.commit()

        resp = await async_client.get(f"{PREFIX}/{project['id']}/milestones/{milestone['id']}/progress")
        assert resp.status_code == 200
        progress = resp.json()["data"]["progress"]
        assert progress["totalTasks"] == 2
        assert progress["completedTasks"] == 1
        assert progress["progress"] == 50.0

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

    @pytest.mark.asyncio
    async def test_import_assessment_artifact_creates_milestones_and_tasks(
        self,
        async_client: httpx.AsyncClient,
    ) -> None:
        project = await _create_project(async_client, "Import Assessment Test")
        artifact_id = await _seed_artifact_with_markdown(
            """
## Milestone Alpha
Phase one execution scope.
- [ ] Define architecture baseline
- [ ] Implement API adapter

## Milestone Beta
Phase two execution scope.
- [ ] Add frontend integration
""",
            chat_id="chat-import-seed",
        )

        resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones/import-assessment",
            json={"artifact_id": artifact_id},
        )
        assert resp.status_code == 200
        receipt = resp.json()["data"]["receipt"]
        assert receipt["total_milestones"] == 2
        assert receipt["total_tasks"] == 3
        imported = receipt["imported_milestones"]
        assert len(imported) == 2

        for row in imported:
            progress_resp = await async_client.get(
                f"{PREFIX}/{project['id']}/milestones/{row['milestone_id']}/progress"
            )
            assert progress_resp.status_code == 200
            progress = progress_resp.json()["data"]["progress"]
            assert progress["totalTasks"] == row["task_count"]
            assert progress["completedTasks"] == 0

    @pytest.mark.asyncio
    async def test_import_assessment_artifact_missing_returns_404(self, async_client: httpx.AsyncClient) -> None:
        project = await _create_project(async_client, "Missing Artifact Test")
        resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones/import-assessment",
            json={"artifact_id": "nonexistent-artifact"},
        )
        assert resp.status_code == 404
        assert _error_issues_by_field(resp, "import_reason") == ["artifact_not_found"]

    @pytest.mark.asyncio
    async def test_import_assessment_project_missing_returns_404(self, async_client: httpx.AsyncClient) -> None:
        resp = await async_client.post(
            f"{PREFIX}/missing-project-id/milestones/import-assessment",
            json={"artifact_id": "any-artifact-id"},
        )
        assert resp.status_code == 404
        assert _error_issues_by_field(resp, "import_reason") == ["project_not_found"]

    @pytest.mark.asyncio
    async def test_import_assessment_artifact_duplicate_version_rejected(
        self,
        async_client: httpx.AsyncClient,
    ) -> None:
        project = await _create_project(async_client, "Duplicate Import Guard")
        artifact_id = await _seed_artifact_with_markdown(
            """
## Milestone Dup
- [ ] Keep import idempotent
""",
            chat_id="chat-import-dup",
        )
        first_resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones/import-assessment",
            json={"artifact_id": artifact_id},
        )
        assert first_resp.status_code == 200

        async with get_session() as db:
            board_stmt = select(KanbanBoardModel).where(KanbanBoardModel.project_id == project["id"])
            board = (await db.execute(board_stmt)).scalar_one()
            board.description = "manually edited description"
            await db.commit()

        duplicate_resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones/import-assessment",
            json={"artifact_id": artifact_id},
        )
        assert duplicate_resp.status_code == 409
        assert "already imported" in duplicate_resp.text.lower()
        assert _error_issues_by_field(duplicate_resp, "import_reason") == [
            "artifact_version_already_imported"
        ]

        milestones_resp = await async_client.get(f"{PREFIX}/{project['id']}/milestones")
        assert milestones_resp.status_code == 200
        assert len(milestones_resp.json()["data"]["milestones"]) == 1

    @pytest.mark.asyncio
    async def test_import_assessment_artifact_rejects_non_actionable_checklists(
        self,
        async_client: httpx.AsyncClient,
    ) -> None:
        project = await _create_project(async_client, "Non Actionable Import Guard")
        artifact_id = await _seed_artifact_with_markdown(
            """
## Milestone Context
- [ ] Notes: captured meeting context
- [ ] Background: discuss constraints
""",
            chat_id="chat-import-non-actionable",
        )
        resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones/import-assessment",
            json={"artifact_id": artifact_id},
        )
        assert resp.status_code == 422
        assert "none are actionable tasks" in resp.text.lower()
        assert _error_issues_by_field(resp, "import_reason") == ["no_actionable_tasks"]

    @pytest.mark.asyncio
    async def test_import_assessment_artifact_rejects_empty_checklist_content(
        self,
        async_client: httpx.AsyncClient,
    ) -> None:
        project = await _create_project(async_client, "No Task Checklist Guard")
        artifact_id = await _seed_artifact_with_markdown(
            """
## Milestone Context
Only narrative text here.
""",
            chat_id="chat-import-no-tasks",
        )
        resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones/import-assessment",
            json={"artifact_id": artifact_id},
        )
        assert resp.status_code == 422
        assert "does not contain importable task list items" in resp.text.lower()
        assert _error_issues_by_field(resp, "import_reason") == ["no_importable_tasks"]

    @pytest.mark.asyncio
    async def test_import_assessment_artifact_rolls_back_on_task_failure(
        self,
        async_client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        project = await _create_project(async_client, "Rollback Fault Injection")
        artifact_id = await _seed_artifact_with_markdown(
            """
## Milestone Rollback
- [ ] First actionable task
- [ ] Second actionable task
""",
            chat_id="chat-import-rollback",
        )
        kanban_service = KanbanService.get_instance()
        original_add_task = kanban_service.add_task
        call_count = 0

        async def flaky_add_task(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("injected task failure")
            return await original_add_task(*args, **kwargs)

        monkeypatch.setattr(kanban_service, "add_task", flaky_add_task)

        resp = await async_client.post(
            f"{PREFIX}/{project['id']}/milestones/import-assessment",
            json={"artifact_id": artifact_id},
        )
        assert resp.status_code == 500

        milestones_resp = await async_client.get(f"{PREFIX}/{project['id']}/milestones")
        assert milestones_resp.status_code == 200
        assert milestones_resp.json()["data"]["milestones"] == []

        async with get_session() as db:
            board_stmt = select(KanbanBoardModel.id).where(KanbanBoardModel.project_id == project["id"])
            board_ids = (await db.execute(board_stmt)).scalars().all()
        assert board_ids == []

        async with get_session() as db:
            stmt = select(AssessmentImportLedger).where(
                AssessmentImportLedger.project_id == project["id"],
                AssessmentImportLedger.artifact_id == artifact_id,
            )
            rows = (await db.execute(stmt)).scalars().all()
        assert rows == []
