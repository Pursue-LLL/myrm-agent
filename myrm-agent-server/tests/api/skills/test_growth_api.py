"""Regression tests for the unified skill growth API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api.skills.evolution import router as evolution_router
from app.api.skills.growth import router as growth_router
from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine
from app.services.skills.draft_notification import notify_skill_draft_created
from app.services.skills.evolution_reviews import create_evolution_review_record


@pytest.fixture(scope="function")
def app() -> FastAPI:
    test_app = FastAPI(title="Skill Growth API Test App")
    test_app.include_router(growth_router, prefix="/api/v1", tags=["skill-growth"])
    test_app.include_router(evolution_router, prefix="/api/v1", tags=["evolution"])
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
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.mark.asyncio
async def test_skill_growth_cases_combine_drafts_and_approval_backed_evolutions(client: TestClient) -> None:
    draft = await notify_skill_draft_created(
        {
            "has_value": True,
            "user_id": f"growth_api_{uuid4().hex}",
            "type": "skill_draft",
            "skill_name": "growth-api-draft",
            "skill_description": "Unified growth case from approval record",
            "trigger_condition": "When the user repeats the same workflow",
            "skill_steps": "1. Inspect\n2. Save",
        }
    )

    evolution = await create_evolution_review_record(
        agent_id="growth-api-test",
        chat_id=None,
        proposal_skill_id="approval-backed-evolution-skill",
        skill_name="approval-backed-evolution-skill",
        skill_path="/tmp/approval-backed-evolution-skill.md",
        evolution_type="fix",
        reason="Approval-backed evolution is awaiting manual review",
        original_content="def current():\n    pass\n",
        evolved_content="def current():\n    return 1\n",
        confidence=0.72,
        test_passed=True,
        task_context="growth api regression",
    )

    response = client.get("/api/v1/skill-growth/cases?limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True

    items = body["data"]["items"]
    sources = {item["source"] for item in items}
    assert "draft" in sources
    assert "evolution" in sources
    assert any(item["id"] == f"draft:{draft.id}" for item in items)
    evolution_item = next(item for item in items if item["id"] == f"evolution:{evolution.id}")
    assert evolution_item["status"] == "PENDING_REVIEW"
    assert evolution_item["apply_status"] == "NOT_APPLIED"
    assert evolution_item["has_diff"] is True
    assert "original_content" not in evolution_item
    assert "proposed_content" not in evolution_item

    detail_response = client.get(f"/api/v1/skill-growth/cases/evolution:{evolution.id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()["data"]
    assert detail["original_content"] == "def current():\n    pass\n"
    assert detail["proposed_content"] == "def current():\n    return 1\n"


@pytest.mark.asyncio
async def test_skill_growth_audit_reads_negative_ledger_events(client: TestClient) -> None:
    async with get_session() as db:
        db.add_all(
            [
                ExperienceLedgerEvent(
                    id="growth-audit-rejected",
                    namespace="default",
                    event_type="skill_growth.rejected",
                    entity_type="skill_growth",
                    entity_id="draft-case-1",
                    lineage_id="skill_growth:draft-case-1",
                    outcome="rejected",
                    summary="The proposal should not be applied",
                    artifact_refs={
                        "skill_id": "skill-a",
                        "skill_name": "skill-a",
                        "draft_type": "skill_patch",
                    },
                    metrics_snapshot={"confidence": 0.9},
                    detail={"status": "REJECTED", "severity": "warning"},
                    created_at=datetime.now(UTC),
                ),
                ExperienceLedgerEvent(
                    id="growth-audit-scan",
                    namespace="default",
                    event_type="skill_growth.failed_scan",
                    entity_type="skill_growth",
                    entity_id="draft-case-2",
                    lineage_id="skill_growth:draft-case-2",
                    outcome="failed_scan",
                    summary="Critical command detected during pre-flight scan",
                    artifact_refs={
                        "skill_id": "skill-b",
                        "skill_name": "skill-b",
                        "draft_type": "skill_draft",
                    },
                    metrics_snapshot={"confidence": 0.4},
                    detail={"status": "FAILED_SCAN", "severity": "critical"},
                    created_at=datetime.now(UTC),
                ),
            ]
        )
        await db.commit()

    audit_response = client.get("/api/v1/skill-growth/audit?limit=10&days=30")
    assert audit_response.status_code == 200
    audit_body = audit_response.json()["data"]
    assert audit_body["total"] == 2
    assert {item["status"] for item in audit_body["items"]} == {"REJECTED", "FAILED_SCAN"}

    stats_response = client.get("/api/v1/skill-growth/audit/stats?time_range_days=30")
    assert stats_response.status_code == 200
    stats_body = stats_response.json()["data"]
    assert stats_body["total_events"] == 2
    assert len(stats_body["by_status"]) == 2
    assert len(stats_body["top_skills"]) == 2
