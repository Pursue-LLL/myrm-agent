"""Tests for SkillRescanService and API endpoints."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.api import (
    SkillRescanResult,
)
from myrm_agent_harness.backends.skills.scanning.scanner import (
    ScanSeverity,
    SkillTrustRecommendation,
)
from myrm_agent_harness.backends.skills.scanning.security_advisories import AdvisoryFinding

from app.core.skills.discovery.rescan_service import SkillRescanService


@pytest.mark.asyncio
async def test_rescan_service_quarantine_flow(tmp_path: Path) -> None:
    service = SkillRescanService(acks_file=tmp_path / "acks.json")

    mock_res = SkillRescanResult(
        skill_name="malicious-skill",
        recommendation=SkillTrustRecommendation.REJECT,
        advisory_findings=[
            AdvisoryFinding(
                advisory_id="MAL-2021-001",
                package_name="ua-parser-js",
                ecosystem="npm",
                severity=ScanSeverity.CRITICAL,
                title="Trojanized package",
                description="Miner injection",
                matched_version="0.7.29",
            )
        ],
    )

    with (
        patch("app.core.skills.discovery.rescan_service.LOCAL_INSTALL_DIR", tmp_path),
        patch.object(service._engine, "rescan_all_installed_skills", AsyncMock(return_value={"malicious-skill": mock_res})),
        patch("app.core.skills.store.service.skills_service.user_config.disable_local_skill", AsyncMock()) as mock_disable,
        patch("app.core.skills.discovery.rescan_service.get_event_bus") as mock_bus_fn,
    ):
        mock_bus = AsyncMock()
        mock_bus_fn.return_value = mock_bus

        report = await service.rescan_skills(user_id="test_user", auto_quarantine=True)
        assert report.total_scanned == 1
        assert report.quarantined_count == 1
        assert mock_disable.called is True
        assert mock_bus.publish.called is True


def test_rescan_service_advisory_acks(tmp_path: Path) -> None:
    service = SkillRescanService(acks_file=tmp_path / "acks.json")
    ack = service.ack_advisory("MAL-001", "pkg-x", "Reviewed safe")
    assert ack.advisory_id == "MAL-001"
    assert len(service.list_acks()) == 1

    assert service.unack_advisory("MAL-001", "pkg-x") is True
    assert len(service.list_acks()) == 0
