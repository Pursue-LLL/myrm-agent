"""[POS]: tests/api/memory/test_job_compounding_api.py
[INPUT]: Isolated FastAPI test application and httpx AsyncClient.
[OUTPUT]: Comprehensive integration tests verifying 4-pillar job description, approval boundaries, rule compounding, and maturity evaluation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.job_compounding_router import (
    router as job_compounding_router,
)
from app.services.memory.job_compounding_service import (
    DomainJobCompoundingService,
    get_job_compounding_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> DomainJobCompoundingService:
    """Provides a fresh DomainJobCompoundingService instance with isolated temporary storage."""
    service = DomainJobCompoundingService(workspace_dir=tmp_path / "sandbox_workspace")
    return service


@pytest.fixture
def test_app(isolated_service: DomainJobCompoundingService) -> FastAPI:
    """Creates FastAPI test app overriding get_job_compounding_service with isolated fixture."""
    app = FastAPI()
    app.include_router(job_compounding_router, prefix="/api/memory")
    app.dependency_overrides[get_job_compounding_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_job_description_crud_and_approval_gate_api(test_app: FastAPI) -> None:
    """Verifies 4-pillar job description persistence and approval boundary check."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create 4-pillar job description
        payload_create = {
            "agent_id": "talent_scout_01",
            "job_title": "Executive Talent Scout",
            "target_scope": "Sourcing and evaluating principal engineers across open-source communities",
            "tools_and_sources": ["github_api", "linkedin_scraper", "portfolio_analyzer"],
            "work_style": "rigorous, evidence-driven, concise",
            "autonomous_actions": ["search_profiles", "summarize_contributions", "draft_briefing"],
            "requires_approval_actions": ["send_outreach_email", "schedule_calendar_invite", "archive_candidate"],
        }
        res_create = await client.post("/api/memory/job-compounding/jobs", json=payload_create)
        assert res_create.status_code == 200
        data_create = res_create.json()
        assert data_create["agent_id"] == "talent_scout_01"
        assert data_create["job_title"] == "Executive Talent Scout"
        assert len(data_create["tools_and_sources"]) == 3
        assert len(data_create["approval_boundary"]["autonomous_actions"]) == 3
        assert len(data_create["approval_boundary"]["requires_approval_actions"]) == 3

        # 2. Get job description
        res_get = await client.get("/api/memory/job-compounding/jobs/talent_scout_01")
        assert res_get.status_code == 200
        assert res_get.json()["target_scope"] == payload_create["target_scope"]

        # 3. Get non-existent agent returns 404
        res_not_found = await client.get("/api/memory/job-compounding/jobs/ghost_agent")
        assert res_not_found.status_code == 404

        # 4. Check approval boundary - autonomous action
        res_check_auto = await client.post(
            "/api/memory/job-compounding/approval/check",
            json={"agent_id": "talent_scout_01", "action_name": "search_profiles"},
        )
        assert res_check_auto.status_code == 200
        data_auto = res_check_auto.json()
        assert data_auto["needs_approval"] is False

        # 5. Check approval boundary - high-stakes action
        res_check_appr = await client.post(
            "/api/memory/job-compounding/approval/check",
            json={"agent_id": "talent_scout_01", "action_name": "send_outreach_email"},
        )
        assert res_check_appr.status_code == 200
        data_appr = res_check_appr.json()
        assert data_appr["needs_approval"] is True


@pytest.mark.asyncio
async def test_rule_compounding_and_maturity_growth_api(test_app: FastAPI) -> None:
    """Verifies recording compounded preference rules and maturity evaluation progression."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        agent_id = "sre_bot_02"

        # Initialize job spec
        await client.post(
            "/api/memory/job-compounding/jobs",
            json={
                "agent_id": agent_id,
                "job_title": "Site Reliability Engineer",
                "target_scope": "Observing cluster anomalies and orchestrating rollbacks",
            },
        )

        # 1. Initial maturity evaluation should be rookie
        res_mat_init = await client.get(f"/api/memory/job-compounding/maturity/{agent_id}")
        assert res_mat_init.status_code == 200
        mat_data_init = res_mat_init.json()
        assert mat_data_init["total_rules_count"] == 0
        assert mat_data_init["tier"] == "rookie"

        # 2. Append positive preference rule
        r1 = {
            "agent_id": agent_id,
            "rule_type": "positive_preference",
            "statement": "Always query Prometheus p99 latency metric before initiating node restarts.",
            "trigger_condition": "During node restart triage",
            "evidence_source": "Incident post-mortem #412",
        }
        res_r1 = await client.post("/api/memory/job-compounding/rules", json=r1)
        assert res_r1.status_code == 200
        assert res_r1.json()["rule_type"] == "positive_preference"

        # 3. Append negative constraint rule
        r2 = {
            "agent_id": agent_id,
            "rule_type": "negative_constraint",
            "statement": "Never execute kubectl delete pod --force in production namespace.",
            "trigger_condition": "During cascading crashloop triage",
            "evidence_source": "Cluster outage root-cause audit #108",
        }
        res_r2 = await client.post("/api/memory/job-compounding/rules", json=r2)
        assert res_r2.status_code == 200
        assert res_r2.json()["rule_type"] == "negative_constraint"

        # 4. Append inspection lesson rule
        r3 = {
            "agent_id": agent_id,
            "rule_type": "inspection_lesson",
            "statement": "Check kernel OOM killer logs via dmesg if container terminates with code 137.",
            "trigger_condition": "Container exit code 137",
            "evidence_source": "Runbook troubleshooting review",
        }
        res_r3 = await client.post("/api/memory/job-compounding/rules", json=r3)
        assert res_r3.status_code == 200
        assert res_r3.json()["rule_type"] == "inspection_lesson"

        # 5. List rules with filtering
        res_all_rules = await client.get(f"/api/memory/job-compounding/rules/{agent_id}")
        assert res_all_rules.status_code == 200
        assert len(res_all_rules.json()) == 3

        res_neg_rules = await client.get(
            f"/api/memory/job-compounding/rules/{agent_id}?rule_type=negative_constraint"
        )
        assert res_neg_rules.status_code == 200
        assert len(res_neg_rules.json()) == 1
        assert res_neg_rules.json()[0]["rule_type"] == "negative_constraint"

        # 6. Evaluate grown maturity report
        res_mat_grown = await client.get(f"/api/memory/job-compounding/maturity/{agent_id}")
        assert res_mat_grown.status_code == 200
        mat_data_grown = res_mat_grown.json()
        assert mat_data_grown["total_rules_count"] == 3
        assert mat_data_grown["positive_preferences_count"] == 1
        assert mat_data_grown["negative_constraints_count"] == 1
        assert mat_data_grown["inspection_lessons_count"] == 1
        assert mat_data_grown["maturity_score"] > 0.0
