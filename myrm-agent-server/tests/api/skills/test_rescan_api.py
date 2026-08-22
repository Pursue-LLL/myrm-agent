"""API tests for skills rescan and advisory endpoints."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.api.skills.rescan import router
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.backends.skills.scanning.rescan_engine import (
    SkillRescanResult,
)
from myrm_agent_harness.backends.skills.scanning.scanner import (
    ScanSeverity,
    SkillTrustRecommendation,
)
from myrm_agent_harness.backends.skills.scanning.security_advisories import AdvisoryFinding

app = FastAPI()
app.include_router(router, prefix="/api/skills")
client = TestClient(app)


def test_api_advisory_acks_flow() -> None:
    # 1. Ack an advisory
    resp = client.post(
        "/api/skills/advisories/ack",
        json={
            "advisory_id": "MAL-2021-001",
            "package_name": "ua-parser-js",
            "reason": "Test acked",
            "acked_by": "admin",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["advisory_id"] == "MAL-2021-001"
    assert data["package_name"] == "ua-parser-js"

    # 2. List acks
    resp_list = client.get("/api/skills/advisories/acks")
    assert resp_list.status_code == 200
    acks = resp_list.json()
    assert len(acks) >= 1
    assert any(a["advisory_id"] == "MAL-2021-001" for a in acks)

    # 3. Unack advisory
    resp_unack = client.post(
        "/api/skills/advisories/unack",
        json={
            "advisory_id": "MAL-2021-001",
            "package_name": "ua-parser-js",
        },
    )
    assert resp_unack.status_code == 200
    assert resp_unack.json()["success"] is True


def test_api_trigger_rescan() -> None:
    mock_res = SkillRescanResult(
        skill_name="sample-skill",
        recommendation=SkillTrustRecommendation.TRUSTED,
    )
    with (
        patch("app.api.skills.rescan.require_local_skills_capability"),
        patch("app.core.skills.discovery.rescan_service.rescan_service.rescan_skills") as mock_rescan,
    ):
        from app.core.skills.discovery.rescan_service import RescanReport, SkillRescanItem

        mock_report = RescanReport(
            total_scanned=1,
            clean_count=1,
            quarantined_count=0,
            items=[
                SkillRescanItem(
                    skill_name="sample-skill",
                    recommendation="trusted",
                    is_clean=True,
                    has_critical_or_malware=False,
                    quarantined=False,
                    summary="Clean",
                    declared_dependencies_count=0,
                    unacked_advisories_count=0,
                    acked_advisories_count=0,
                    findings_count=0,
                )
            ],
            results={"sample-skill": mock_res},
        )
        mock_rescan.return_value = mock_report

        resp = client.post(
            "/api/skills/rescan",
            json={"skill_id": "sample-skill", "enable_online_osv": False, "auto_quarantine": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scanned"] == 1
        assert data["clean_count"] == 1
        assert data["items"][0]["skill_name"] == "sample-skill"

        # Check last report endpoint
        resp_last = client.get("/api/skills/rescan/report")
        assert resp_last.status_code == 200
        assert resp_last.json()["total_scanned"] == 1
