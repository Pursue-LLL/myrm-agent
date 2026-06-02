"""Regression tests for skill-growth projections under the experience ledger API."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.skills.experience_ledger import router as experience_ledger_router
from app.database.connection import get_session
from app.database.models import Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine


@pytest.fixture(scope="function")
def app() -> FastAPI:
    test_app = FastAPI(title="Experience Ledger Skill Growth API Test App")
    test_app.include_router(experience_ledger_router, prefix="/api/v1", tags=["experience-ledger"])
    return test_app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
async def setup_database() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.commit()


@pytest.mark.asyncio
async def test_skill_growth_projection_endpoints_return_normalized_views(client: TestClient) -> None:
    async with get_session() as db:
        db.add_all(
            [
                ExperienceLedgerEvent(
                    id="skill-growth-pending",
                    namespace="default",
                    event_type="skill_growth.review_required",
                    entity_type="skill_growth",
                    entity_id="draft-case-1",
                    lineage_id="skill_growth:draft-case-1",
                    outcome="pending_review",
                    summary="Queued for manual review",
                    artifact_refs={
                        "skill_id": "draft-skill",
                        "skill_name": "draft-skill",
                        "draft_type": "skill_draft",
                    },
                    metrics_snapshot={"confidence": 0.62},
                    detail={"status": "PENDING_REVIEW", "draft_type": "skill_draft"},
                    created_at=datetime.now(UTC),
                ),
                ExperienceLedgerEvent(
                    id="skill-growth-rejected",
                    namespace="default",
                    event_type="skill_growth.rejected",
                    entity_type="skill_growth",
                    entity_id="draft-case-2",
                    lineage_id="skill_growth:draft-case-2",
                    outcome="rejected",
                    summary="Rejected after manual review",
                    artifact_refs={
                        "skill_id": "draft-skill-2",
                        "skill_name": "draft-skill-2",
                        "draft_type": "skill_patch",
                    },
                    metrics_snapshot={"confidence": 0.44},
                    detail={"status": "REJECTED", "draft_type": "skill_patch"},
                    created_at=datetime.now(UTC),
                ),
                ExperienceLedgerEvent(
                    id="evolution-apply-failed",
                    namespace="default",
                    event_type="evolution.apply_failed",
                    entity_type="evolution",
                    entity_id="evolution-case-1",
                    lineage_id="evolution:evolution-case-1",
                    outcome="apply_failed",
                    summary="Patch application failed due to file lock",
                    artifact_refs={
                        "skill_id": "evolution-skill",
                        "skill_name": "evolution-skill",
                    },
                    metrics_snapshot={"confidence": 0.81},
                    detail={"status": "APPLY_FAILED", "evolution_type": "patch"},
                    created_at=datetime.now(UTC),
                ),
                ExperienceLedgerEvent(
                    id="legacy-evolution-rejected",
                    namespace="default",
                    event_type="evolution.rejected",
                    entity_type="evolution",
                    entity_id="legacy-case-1",
                    lineage_id="evolution:legacy-case-1",
                    outcome="rejected",
                    summary="Legacy evolution rejection should not leak into skill-growth projections",
                    artifact_refs={
                        "skill_id": "legacy-skill",
                        "skill_name": "legacy-skill",
                    },
                    metrics_snapshot={"confidence": 0.1},
                    detail={"status": "REJECTED"},
                    created_at=datetime.now(UTC),
                ),
            ]
        )
        await db.commit()

    events_response = client.get("/api/v1/experience-ledger/skill-growth/events?limit=10")
    assert events_response.status_code == 200
    events_body = events_response.json()
    assert events_body["total"] == 3
    assert {item["status"] for item in events_body["items"]} == {
        "PENDING_REVIEW",
        "REJECTED",
        "APPLY_FAILED",
    }
    assert {item["source"] for item in events_body["items"]} == {"draft", "evolution"}
    assert {item["skill_id"] for item in events_body["items"]} == {
        "draft-skill",
        "draft-skill-2",
        "evolution-skill",
    }

    negative_response = client.get("/api/v1/experience-ledger/skill-growth/events?limit=10&negative_only=true")
    assert negative_response.status_code == 200
    negative_body = negative_response.json()
    assert negative_body["total"] == 2
    assert {item["status"] for item in negative_body["items"]} == {"REJECTED", "APPLY_FAILED"}

    summary_response = client.get("/api/v1/experience-ledger/skill-growth/summary")
    assert summary_response.status_code == 200
    summary_body = summary_response.json()
    assert summary_body["total_events"] == 3
    assert summary_body["pending_events"] == 1
    assert summary_body["rejected"] == 1
    assert summary_body["negative_events"] == 2
    assert summary_body["apply_failed"] == 1
    assert summary_body["by_status"]["PENDING_REVIEW"] == 1
    assert summary_body["by_status"]["REJECTED"] == 1
    assert summary_body["by_status"]["APPLY_FAILED"] == 1
