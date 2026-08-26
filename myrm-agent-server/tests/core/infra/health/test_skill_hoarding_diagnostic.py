"""Unit tests for SkillHoardingHealthDiagnostic probe."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.backends.skills.forgetting_strategy import CuratorConfig
from myrm_agent_harness.backends.skills.types import (
    SkillLifecycleStatus,
    SkillTrust,
    SkillUsageStats,
)

from app.core.infra.health.agent_diagnostics import SkillHoardingHealthDiagnostic
from app.core.infra.health.server_diagnostics import (
    ServerDiagnosticsManager,
    run_server_diagnostics,
)


@dataclass
class _FakeSkill:
    name: str
    usage_stats: SkillUsageStats
    trust: SkillTrust = SkillTrust.TRUSTED
    evolution_locked: bool = False
    storage_path: str = "/skills/test_skill"


@pytest.mark.asyncio
async def test_skill_hoarding_diagnostic_healthy_pass(tmp_path: Path) -> None:
    """Test when skill catalog is within budget and all skills have good success rate."""
    diagnostic = SkillHoardingHealthDiagnostic()
    config = CuratorConfig(max_skills=50, min_call_count_for_quality_check=5, min_success_rate=0.3)

    skills = [
        _FakeSkill(
            name=f"good_skill_{i}",
            usage_stats=SkillUsageStats(
                call_count=10,
                success_count=9,
                failure_count=1,
                lifecycle_status=SkillLifecycleStatus.ACTIVE,
            ),
        )
        for i in range(15)
    ]

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.curator.service.get_stats_collector", return_value=MagicMock()),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch("myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills", AsyncMock(return_value=skills)),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "SkillEcosystem"
        assert report.status == "pass"
        assert report.code == "OK_SKILL_ECOSYSTEM_HEALTHY"
        assert report.meta_data is not None
        assert report.meta_data["active_skills_count"] == 15
        assert report.meta_data["wrong_but_frequent_count"] == 0
        assert report.metrics["wrong_but_frequent_count"] == 0.0


@pytest.mark.asyncio
async def test_skill_hoarding_diagnostic_warning_near_capacity(tmp_path: Path) -> None:
    """Test warning status when active skills reach 80% capacity."""
    diagnostic = SkillHoardingHealthDiagnostic()
    config = CuratorConfig(max_skills=50, min_call_count_for_quality_check=5, min_success_rate=0.3)

    skills = [
        _FakeSkill(
            name=f"skill_{i}",
            usage_stats=SkillUsageStats(
                call_count=2,
                success_count=2,
                failure_count=0,
                lifecycle_status=SkillLifecycleStatus.ACTIVE,
            ),
        )
        for i in range(42)  # 42 >= 50 * 0.8
    ]

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.curator.service.get_stats_collector", return_value=MagicMock()),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch("myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills", AsyncMock(return_value=skills)),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "SkillEcosystem"
        assert report.status == "warn"
        assert report.code == "WARN_SKILL_HOARDING_OR_FAULTY"
        assert report.meta_data is not None
        assert report.meta_data["active_skills_count"] == 42


@pytest.mark.asyncio
async def test_skill_hoarding_diagnostic_warning_wrong_but_frequent(tmp_path: Path) -> None:
    """Test warning when a skill is frequently called but fails constantly."""
    diagnostic = SkillHoardingHealthDiagnostic()
    config = CuratorConfig(max_skills=50, min_call_count_for_quality_check=5, min_success_rate=0.3)

    skills = [
        _FakeSkill(
            name="good_skill",
            usage_stats=SkillUsageStats(
                call_count=10,
                success_count=10,
                failure_count=0,
                lifecycle_status=SkillLifecycleStatus.ACTIVE,
            ),
        ),
        _FakeSkill(
            name="buggy_frequent_skill",
            usage_stats=SkillUsageStats(
                call_count=20,
                success_count=2,
                failure_count=18,
                lifecycle_status=SkillLifecycleStatus.ACTIVE,
            ),
        ),
    ]

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.curator.service.get_stats_collector", return_value=MagicMock()),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch("myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills", AsyncMock(return_value=skills)),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "SkillEcosystem"
        assert report.status == "warn"
        assert report.code == "WARN_SKILL_HOARDING_OR_FAULTY"
        assert report.meta_data is not None
        assert report.meta_data["wrong_but_frequent_count"] == 1
        faulty = report.meta_data["wrong_but_frequent_skills"]
        assert isinstance(faulty, list)
        assert len(faulty) == 1
        assert faulty[0]["skill_name"] == "buggy_frequent_skill"
        assert faulty[0]["is_exempt_from_curator"] is False


@pytest.mark.asyncio
async def test_skill_hoarding_diagnostic_critical_hoarding_limit_exceeded(tmp_path: Path) -> None:
    """Test fail status when active skill count exceeds max_skills."""
    diagnostic = SkillHoardingHealthDiagnostic()
    config = CuratorConfig(max_skills=50, min_call_count_for_quality_check=5, min_success_rate=0.3)

    skills = [
        _FakeSkill(
            name=f"skill_{i}",
            usage_stats=SkillUsageStats(
                call_count=1,
                success_count=1,
                failure_count=0,
                lifecycle_status=SkillLifecycleStatus.ACTIVE,
            ),
        )
        for i in range(55)  # 55 > 50
    ]

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.curator.service.get_stats_collector", return_value=MagicMock()),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch("myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills", AsyncMock(return_value=skills)),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "SkillEcosystem"
        assert report.status == "fail"
        assert report.code == "ERR_SKILL_HOARDING_CRITICAL"
        assert "Active skills (55) exceed configured limit (50)" in report.detail


@pytest.mark.asyncio
async def test_skill_hoarding_diagnostic_critical_protected_wrong_skills(tmp_path: Path) -> None:
    """Test fail status when >= 3 wrong-but-frequent skills are pinned/protected from auto-cleanup."""
    diagnostic = SkillHoardingHealthDiagnostic()
    config = CuratorConfig(
        max_skills=50,
        min_call_count_for_quality_check=5,
        min_success_rate=0.3,
        protect_installed_skills=True,
    )

    skills = [
        _FakeSkill(
            name=f"pinned_failing_skill_{i}",
            usage_stats=SkillUsageStats(
                call_count=15,
                success_count=1,
                failure_count=14,
                pinned=True,
                lifecycle_status=SkillLifecycleStatus.ACTIVE,
            ),
        )
        for i in range(3)
    ]

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.curator.service.get_stats_collector", return_value=MagicMock()),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch("myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills", AsyncMock(return_value=skills)),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "SkillEcosystem"
        assert report.status == "fail"
        assert report.code == "ERR_SKILL_HOARDING_CRITICAL"
        assert report.meta_data is not None
        assert report.meta_data["protected_wrong_count"] == 3


@pytest.mark.asyncio
async def test_server_diagnostics_manager_includes_skill_hoarding() -> None:
    """Verify ServerDiagnosticsManager registers SkillHoardingHealthDiagnostic."""
    manager = ServerDiagnosticsManager()
    probe_names = [p.__class__.__name__ for p in manager._probes]
    assert "SkillHoardingHealthDiagnostic" in probe_names

    reports = await run_server_diagnostics()
    component_names = [r.component_name for r in reports]
    assert "SkillEcosystem" in component_names
