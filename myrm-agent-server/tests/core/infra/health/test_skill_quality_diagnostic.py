"""Unit tests for SkillQualityHealthDiagnostic probe."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.market.helpers import write_origin
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
from myrm_agent_harness.backends.skills.types import (
    SkillLifecycleStatus,
    SkillUsageStats,
)

from app.core.infra.health.server_diagnostics import (
    ServerDiagnosticsManager,
    SkillQualityHealthDiagnostic,
    run_server_diagnostics,
)


@dataclass
class _FakeSkill:
    name: str
    usage_stats: SkillUsageStats
    evolution_locked: bool = False
    storage_path: str = "/skills/test_skill"


@pytest.mark.asyncio
async def test_skill_quality_diagnostic_healthy_pass(tmp_path: Path) -> None:
    """Test when all skills have a good success rate."""
    diagnostic = SkillQualityHealthDiagnostic()
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3)

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
        patch(
            "app.core.skills.curator.service.get_stats_collector",
            return_value=MagicMock(),
        ),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch(
            "myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills",
            AsyncMock(return_value=skills),
        ),
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
async def test_skill_quality_diagnostic_large_healthy_library_passes(tmp_path: Path) -> None:
    """The size of the library is not a health signal: 120 healthy skills pass."""
    diagnostic = SkillQualityHealthDiagnostic()
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3)
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
        for i in range(120)
    ]

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch(
            "myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills",
            AsyncMock(return_value=skills),
        ),
    ):
        report = await diagnostic.check_health()

    assert report.status == "pass"
    assert report.code == "OK_SKILL_ECOSYSTEM_HEALTHY"
    assert report.meta_data is not None
    assert report.meta_data["active_skills_count"] == 120


@pytest.mark.asyncio
async def test_skill_quality_diagnostic_warning_wrong_but_frequent(
    tmp_path: Path,
) -> None:
    """Test warning when a skill is frequently called but fails constantly."""
    diagnostic = SkillQualityHealthDiagnostic()
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3)

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
        patch(
            "app.core.skills.curator.service.get_stats_collector",
            return_value=MagicMock(),
        ),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch(
            "myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills",
            AsyncMock(return_value=skills),
        ),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "SkillEcosystem"
        assert report.status == "warn"
        assert report.code == "WARN_SKILL_FAULTY"
        assert report.meta_data is not None
        assert report.meta_data["wrong_but_frequent_count"] == 1
        faulty = report.meta_data["wrong_but_frequent_skills"]
        assert isinstance(faulty, list)
        assert len(faulty) == 1
        assert faulty[0]["skill_name"] == "buggy_frequent_skill"
        assert faulty[0]["is_exempt_from_curator"] is False


@pytest.mark.asyncio
async def test_skill_quality_diagnostic_critical_protected_wrong_skills(
    tmp_path: Path,
) -> None:
    """Test fail status when >= 3 wrong-but-frequent skills are pinned/protected from auto-cleanup."""
    diagnostic = SkillQualityHealthDiagnostic()
    config = CuratorConfig(
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
        patch(
            "app.core.skills.curator.service.get_stats_collector",
            return_value=MagicMock(),
        ),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)]),
        patch(
            "myrm_agent_harness.backends.skills.local.LocalSkillBackend.list_skills",
            AsyncMock(return_value=skills),
        ),
    ):
        report = await diagnostic.check_health()
        assert report.component_name == "SkillEcosystem"
        assert report.status == "fail"
        assert report.code == "ERR_SKILL_PROTECTED_FAULTY"
        assert report.meta_data is not None
        assert report.meta_data["protected_wrong_count"] == 3


def _write_failing_skill(skill_dir: Path, *, from_market: bool) -> None:
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_dir.name}\ndescription: Skill {skill_dir.name}\n---\nBody.\n", encoding="utf-8"
    )
    failing = SkillUsageStats(call_count=10, success_count=1, failure_count=9)
    (skill_dir / ".stats.json").write_text(json.dumps(failing.to_dict()), encoding="utf-8")
    if from_market:
        write_origin(skill_dir, source="registry", skill_id=f"registry::{skill_dir.name}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("protect_installed", "expected_exempt", "expected_reasons"),
    [(True, True, ["installed_protected"]), (False, False, [])],
)
async def test_installed_failing_skill_is_exempt_only_while_protection_is_on(
    tmp_path: Path, protect_installed: bool, expected_exempt: bool, expected_reasons: list[str]
) -> None:
    """The probe reads the same installed/authored split the sweep acts on, from real skill directories."""
    own_root = tmp_path / "skills"
    _write_failing_skill(own_root / "from-store", from_market=True)
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3, protect_installed_skills=protect_installed)

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(own_root)]),
    ):
        report = await SkillQualityHealthDiagnostic().check_health()

    assert report.meta_data is not None
    (finding,) = report.meta_data["wrong_but_frequent_skills"]
    assert finding["skill_name"] == "from-store"
    assert finding["is_exempt_from_curator"] is expected_exempt
    assert finding["exemption_reasons"] == expected_reasons


@pytest.mark.asyncio
async def test_authored_failing_skill_is_never_reported_as_installed(tmp_path: Path) -> None:
    own_root = tmp_path / "skills"
    _write_failing_skill(own_root / "my-notes", from_market=False)
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3, protect_installed_skills=True)

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(own_root)]),
    ):
        report = await SkillQualityHealthDiagnostic().check_health()

    assert report.meta_data is not None
    (finding,) = report.meta_data["wrong_but_frequent_skills"]
    assert finding["is_exempt_from_curator"] is False
    assert finding["exemption_reasons"] == []


@pytest.mark.asyncio
async def test_server_diagnostics_manager_includes_skill_quality() -> None:
    """Verify ServerDiagnosticsManager registers SkillQualityHealthDiagnostic."""
    manager = ServerDiagnosticsManager()
    probe_names = [p.__class__.__name__ for p in manager._probes]
    assert "SkillQualityHealthDiagnostic" in probe_names

    reports = await run_server_diagnostics()
    component_names = [r.component_name for r in reports]
    assert "SkillEcosystem" in component_names
