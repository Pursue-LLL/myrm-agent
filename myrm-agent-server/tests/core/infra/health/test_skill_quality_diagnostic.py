"""Unit tests for SkillQualityHealthDiagnostic probe."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.infra.health.server_diagnostics import (
    ServerDiagnosticsManager,
    SkillQualityHealthDiagnostic,
    run_server_diagnostics,
)
from app.core.skills.curator import bound_skills as bound_skills_module
from app.database.models import Agent, Base


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


@pytest.mark.asyncio
async def test_evolution_locked_faulty_skill_is_not_counted_as_exempt(tmp_path: Path) -> None:
    """The evolution lock guards rewrites, not the lifecycle sweep, so it must not look like cleanup protection.

    The sweep evaluates and transitions a locked skill exactly like an unlocked one, so counting the
    lock as an exemption would hide faulty pinned-free skills behind a guard that does not exist.
    """
    diagnostic = SkillQualityHealthDiagnostic()
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3, protect_installed_skills=True)

    skills = [
        _FakeSkill(
            name=f"locked_failing_skill_{i}",
            usage_stats=SkillUsageStats(
                call_count=15,
                success_count=1,
                failure_count=14,
                lifecycle_status=SkillLifecycleStatus.ACTIVE,
            ),
            evolution_locked=True,
        )
        for i in range(3)
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

    assert report.status == "warn"
    assert report.code == "WARN_SKILL_FAULTY"
    assert report.meta_data is not None
    assert report.meta_data["wrong_but_frequent_count"] == 3
    assert report.meta_data["protected_wrong_count"] == 0
    findings = report.meta_data["wrong_but_frequent_skills"]
    assert isinstance(findings, list)
    assert all(finding["is_exempt_from_curator"] is False for finding in findings)
    assert all(finding["exemption_reasons"] == [] for finding in findings)


async def _raise_if_called(*_args: object) -> frozenset[str]:
    raise AssertionError("binding lookup reached")


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


@pytest.fixture
async def bound_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncSession]:
    """Isolated SQLite DB that ``bound_skill_names`` reads through its own ``get_session``."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bound.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def isolated_session() -> AsyncIterator[AsyncSession]:
        async with factory() as db:
            yield db

    monkeypatch.setattr(bound_skills_module, "get_session", isolated_session)
    async with factory() as seed:
        yield seed
    await engine.dispose()


@pytest.mark.asyncio
async def test_bound_faulty_skill_is_counted_as_exempt(tmp_path: Path, bound_db: AsyncSession) -> None:
    """A skill an agent still binds is exempt from the sweep, so the probe must not report it as cleanable.

    The curator never transitions a bound skill; without the ``bound`` exemption the probe
    under-counts un-cleanable faulty skills and reports ``warn`` instead of ``fail``.
    """
    own_root = tmp_path / "skills"
    _write_failing_skill(own_root / "bound-faulty", from_market=False)
    _write_failing_skill(own_root / "free-faulty", from_market=False)
    bound_db.add(Agent(id="a1", name="mailer", skill_ids=["bound-faulty"]))
    await bound_db.commit()
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3, protect_installed_skills=False)

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(own_root)]),
    ):
        report = await SkillQualityHealthDiagnostic().check_health()

    assert report.meta_data is not None
    assert report.meta_data["wrong_but_frequent_count"] == 2
    assert report.meta_data["protected_wrong_count"] == 1
    by_name = {str(f["skill_name"]): f for f in report.meta_data["wrong_but_frequent_skills"]}
    assert by_name["bound-faulty"]["is_exempt_from_curator"] is True
    assert by_name["bound-faulty"]["exemption_reasons"] == ["bound"]
    assert by_name["free-faulty"]["is_exempt_from_curator"] is False


@pytest.mark.asyncio
async def test_three_bound_faulty_skills_escalate_to_fail(tmp_path: Path, bound_db: AsyncSession) -> None:
    """Bound faulty skills accumulate un-cleanable, exactly like pinned ones, so >= 3 must fail the probe."""
    own_root = tmp_path / "skills"
    names = [f"bound-faulty-{i}" for i in range(3)]
    for name in names:
        _write_failing_skill(own_root / name, from_market=False)
    bound_db.add(Agent(id="a1", name="mailer", skill_ids=names))
    await bound_db.commit()
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3, protect_installed_skills=False)

    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(own_root)]),
    ):
        report = await SkillQualityHealthDiagnostic().check_health()

    assert report.status == "fail"
    assert report.code == "ERR_SKILL_PROTECTED_FAULTY"
    assert report.meta_data is not None
    assert report.meta_data["protected_wrong_count"] == 3


@pytest.mark.asyncio
async def test_healthy_library_does_not_query_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A library with no faulty skill has nothing to exempt, so the probe must not open the database.

    Paired with ``test_faulty_library_does_query_bindings``: the same stub that the faulty case reaches
    is never touched here, so the skip is proven rather than assumed.
    """
    own_root = tmp_path / "skills"
    _write_failing_skill(own_root / "healthy", from_market=False)
    (own_root / "healthy" / ".stats.json").write_text(
        json.dumps(SkillUsageStats(call_count=10, success_count=10, failure_count=0).to_dict()), encoding="utf-8"
    )
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3)

    monkeypatch.setattr(bound_skills_module, "bound_skill_names", _raise_if_called)
    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(own_root)]),
    ):
        report = await SkillQualityHealthDiagnostic().check_health()

    assert report.status == "pass"
    assert report.code == "OK_SKILL_ECOSYSTEM_HEALTHY"


@pytest.mark.asyncio
async def test_faulty_library_does_query_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The counterpart guard: with a faulty skill present the probe does reach the binding lookup."""
    own_root = tmp_path / "skills"
    _write_failing_skill(own_root / "faulty", from_market=False)
    config = CuratorConfig(min_call_count_for_quality_check=5, min_success_rate=0.3)

    monkeypatch.setattr(bound_skills_module, "bound_skill_names", _raise_if_called)
    with (
        patch("app.core.skills.curator.service.get_curator_config", return_value=config),
        patch("app.core.skills.models.DEFAULT_LOCAL_SKILL_PATHS", [str(own_root)]),
    ):
        report = await SkillQualityHealthDiagnostic().check_health()

    assert report.code == "OK_SKILL_ECOSYSTEM_SKIPPED"


@pytest.mark.asyncio
async def test_server_diagnostics_manager_includes_skill_quality() -> None:
    """Verify ServerDiagnosticsManager registers SkillQualityHealthDiagnostic."""
    manager = ServerDiagnosticsManager()
    probe_names = [p.__class__.__name__ for p in manager._probes]
    assert "SkillQualityHealthDiagnostic" in probe_names

    reports = await run_server_diagnostics()
    component_names = [r.component_name for r in reports]
    assert "SkillEcosystem" in component_names
