"""Each doctor finding says whether an agent profile or cron job still binds the skill (real skill dirs, real DB rows)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.curator_config import CuratorConfig
from myrm_agent_harness.backends.skills.local import LocalSkillBackend
from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills import models
from app.core.skills.curator import service
from app.database.models import Agent, CronJobModel

_SCHEDULE = {"kind": "cron", "expr": "0 8 * * *"}


def _write_skill(root: Path, name: str, *, faulty: bool, pinned: bool = False) -> None:
    """A faulty skill ran ten times with a 10% success rate, well past the doctor's thresholds."""
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Skill {name}\n---\nBody.\n", encoding="utf-8")
    used_at = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    successes = 1 if faulty else 10
    ledger = {
        "schema_version": 2,
        "call_count": 10,
        "success_count": successes,
        "failure_count": 10 - successes,
        "last_used_at": used_at,
        "created_at": (datetime.now(UTC) - timedelta(days=60)).isoformat(),
        "lifecycle_status": "active",
        "pinned": pinned,
        "usage_history": [{"timestamp": used_at, "success": not faulty}],
    }
    (skill_dir / ".stats.json").write_text(json.dumps(ledger), encoding="utf-8")


@pytest.fixture
def skills_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(models, "DEFAULT_LOCAL_SKILL_PATHS", [str(root)])
    monkeypatch.setattr(service, "_curator_config", CuratorConfig())
    return root


async def _skill_id(root: Path, name: str) -> str:
    skills = await LocalSkillBackend(root, use_snapshot=False).list_skills()
    skill = next(s for s in skills if s.name == name)
    assert skill.storage_path is not None
    return local_skill_id_from_path(Path(skill.storage_path))


async def _findings() -> list[dict[str, object]]:
    findings = (await service.get_skill_diagnostics())["findings"]
    assert isinstance(findings, list)
    return findings


async def _bound_by_findings() -> dict[str, bool]:
    return {str(f["skill_name"]): bool(f["bound"]) for f in await _findings()}


async def test_faulty_skill_bound_by_a_cron_job_is_marked_bound(skills_root: Path, session: AsyncSession) -> None:
    _write_skill(skills_root, "email-digest", faulty=True)
    _write_skill(skills_root, "scratch-notes", faulty=True)
    session.add(
        CronJobModel(
            id="j1",
            name="morning digest",
            job_type="agent",
            schedule=_SCHEDULE,
            status="active",
            skill_ids=[await _skill_id(skills_root, "email-digest")],
        )
    )
    await session.commit()

    assert await _bound_by_findings() == {"email-digest": True, "scratch-notes": False}


async def test_pinned_faulty_skill_bound_by_an_agent_is_marked_bound(skills_root: Path, session: AsyncSession) -> None:
    _write_skill(skills_root, "email-digest", faulty=True, pinned=True)
    session.add(Agent(id="a1", name="mailer", skill_ids=[await _skill_id(skills_root, "email-digest")]))
    await session.commit()

    (finding,) = await _findings()

    assert finding["pinned"] is True
    assert finding["bound"] is True


async def test_healthy_bound_skill_has_no_finding(skills_root: Path, session: AsyncSession) -> None:
    _write_skill(skills_root, "email-digest", faulty=False)
    session.add(Agent(id="a1", name="mailer", skill_ids=[await _skill_id(skills_root, "email-digest")]))
    await session.commit()

    assert await _bound_by_findings() == {}


async def test_clean_library_does_not_query_bindings(skills_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_skill(skills_root, "email-digest", faulty=False)

    async def fail_if_called(*_args: object) -> frozenset[str]:
        raise AssertionError("a library without findings has nothing to look up")

    monkeypatch.setattr(service, "bound_skill_names", fail_if_called)

    assert await _bound_by_findings() == {}
