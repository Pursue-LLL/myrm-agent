from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.database.connection import get_session
from app.database.models import (
    AssessmentImportLedger,
    KanbanBoardModel,
    KanbanTaskModel,
    Milestone,
    Project,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="statistics")


def _assessment_import_meta(project_id: str, artifact_version_id: str, milestone_id: str) -> dict[str, object]:
    return {
        "assessment_import": {
            "project_id": project_id,
            "artifact_version_id": artifact_version_id,
            "milestone_id": milestone_id,
        }
    }


@pytest.mark.asyncio
async def test_assessment_import_value_summary_supports_project_scope() -> None:
    now = datetime.now(timezone.utc)
    suffix = uuid4().hex[:8]
    proj_value = f"proj-value-{suffix}"
    proj_other = f"proj-other-{suffix}"

    async with get_session() as db:
        db.add_all([Project(id=proj_value, name="Value Project"), Project(id=proj_other, name="Other Project")])
        await db.commit()

        db.add_all(
            [
                Milestone(
                    id=f"ms-value-1-{suffix}",
                    project_id=proj_value,
                    title="Value Milestone 1",
                    status="completed",
                    sort_order=0,
                    completed_at=now,
                ),
                Milestone(
                    id=f"ms-value-2-{suffix}",
                    project_id=proj_value,
                    title="Value Milestone 2",
                    status="active",
                    sort_order=1,
                ),
                Milestone(
                    id=f"ms-other-1-{suffix}",
                    project_id=proj_other,
                    title="Other Milestone 1",
                    status="completed",
                    sort_order=0,
                    completed_at=now,
                ),
            ]
        )
        await db.commit()

        db.add_all(
            [
                KanbanBoardModel(
                    id=f"board-value-1-{suffix}",
                    name="Value Board 1",
                    project_id=proj_value,
                    milestone_id=f"ms-value-1-{suffix}",
                ),
                KanbanBoardModel(
                    id=f"board-value-2-{suffix}",
                    name="Value Board 2",
                    project_id=proj_value,
                    milestone_id=f"ms-value-2-{suffix}",
                ),
                KanbanBoardModel(
                    id=f"board-other-1-{suffix}",
                    name="Other Board 1",
                    project_id=proj_other,
                    milestone_id=f"ms-other-1-{suffix}",
                ),
            ]
        )
        await db.commit()

        db.add_all(
            [
                KanbanTaskModel(
                    id=f"task-value-1-{suffix}",
                    board_id=f"board-value-1-{suffix}",
                    title="Task 1",
                    status="completed",
                    metadata_json=_assessment_import_meta(proj_value, f"ver-value-1-{suffix}", f"ms-value-1-{suffix}"),
                ),
                KanbanTaskModel(
                    id=f"task-value-2-{suffix}",
                    board_id=f"board-value-1-{suffix}",
                    title="Task 2",
                    status="ready",
                    metadata_json=_assessment_import_meta(proj_value, f"ver-value-1-{suffix}", f"ms-value-1-{suffix}"),
                ),
                KanbanTaskModel(
                    id=f"task-value-3-{suffix}",
                    board_id=f"board-value-2-{suffix}",
                    title="Task 3",
                    status="completed",
                    metadata_json=_assessment_import_meta(proj_value, f"ver-value-1-{suffix}", f"ms-value-2-{suffix}"),
                ),
                KanbanTaskModel(
                    id=f"task-other-1-{suffix}",
                    board_id=f"board-other-1-{suffix}",
                    title="Other Task 1",
                    status="completed",
                    metadata_json=_assessment_import_meta(proj_other, f"ver-other-1-{suffix}", f"ms-other-1-{suffix}"),
                ),
            ]
        )
        db.add_all(
            [
                AssessmentImportLedger(
                    project_id=proj_value,
                    artifact_id=f"artifact-value-{suffix}",
                    artifact_version_id=f"ver-value-1-{suffix}",
                    status="completed",
                    total_milestones=2,
                    total_tasks=3,
                    created_at=now,
                ),
                AssessmentImportLedger(
                    project_id=proj_other,
                    artifact_id=f"artifact-other-{suffix}",
                    artifact_version_id=f"ver-other-1-{suffix}",
                    status="completed",
                    total_milestones=1,
                    total_tasks=1,
                    created_at=now,
                ),
            ]
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        scoped_response = await ac.get(f"/api/v1/statistics/assessment-import/value-summary?days=30&project_id={proj_value}")
        assert scoped_response.status_code == 200
        scoped_data = scoped_response.json()["data"]
        assert scoped_data["project_id"] == proj_value
        assert scoped_data["imports_total"] == 1
        assert scoped_data["imports_with_task_completion"] == 1
        assert scoped_data["imports_with_milestone_completion"] == 1
        assert scoped_data["imported_tasks_total"] == 3
        assert scoped_data["completed_tasks_total"] == 2
        assert scoped_data["imported_milestones_total"] == 2
        assert scoped_data["completed_milestones_total"] == 1
        assert scoped_data["task_completion_rate"] == 0.6667
        assert scoped_data["milestone_completion_rate"] == 0.5
        assert scoped_data["import_activation_rate"] == 1.0

        global_response = await ac.get("/api/v1/statistics/assessment-import/value-summary?days=30")
        assert global_response.status_code == 200
        global_data = global_response.json()["data"]
        assert global_data["project_id"] is None
        assert global_data["imports_total"] >= 2
        assert global_data["imported_tasks_total"] >= 4
        assert global_data["completed_tasks_total"] >= 3


@pytest.mark.asyncio
async def test_assessment_import_value_summary_filters_by_days() -> None:
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(days=45)
    suffix = uuid4().hex[:8]
    project_id = f"proj-window-{suffix}"

    async with get_session() as db:
        db.add(Project(id=project_id, name="Window Project"))
        await db.commit()

        db.add(
            AssessmentImportLedger(
                project_id=project_id,
                artifact_id=f"artifact-old-{suffix}",
                artifact_version_id=f"ver-old-{suffix}",
                status="completed",
                total_milestones=1,
                total_tasks=2,
                created_at=old_time,
            )
        )
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(f"/api/v1/statistics/assessment-import/value-summary?days=30&project_id={project_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["imports_total"] == 0
        assert data["imported_tasks_total"] == 0
        assert data["completed_tasks_total"] == 0
