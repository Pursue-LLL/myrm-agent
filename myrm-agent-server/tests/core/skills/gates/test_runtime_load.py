"""Runtime load gate: archived and disabled skills must not enter agent backend."""

from __future__ import annotations

from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus

from app.core.skills.gates.runtime_load import (
    filter_skills_for_runtime_load,
    skill_runtime_load_block_reason,
)
from app.core.skills.models import Skill
from app.core.storage.types import SkillType


def _skill(
    skill_id: str = "s1",
    *,
    skill_type: SkillType = SkillType.LOCAL,
    lifecycle: str | None = None,
) -> Skill:
    usage_stats = {"lifecycle_status": lifecycle} if lifecycle else None
    return Skill(
        id=skill_id,
        type=skill_type,
        name="demo-skill",
        description="d",
        storage_path="/tmp/demo",
        usage_stats=usage_stats,
    )


def test_archived_local_skill_blocked() -> None:
    skill = _skill(lifecycle=SkillLifecycleStatus.ARCHIVED.value)
    reason = skill_runtime_load_block_reason(
        skill,
        enabled_prebuilt_ids=set(),
        enabled_local_ids={"s1"},
    )
    assert reason == "archived"


def test_disabled_local_skill_blocked() -> None:
    skill = _skill()
    reason = skill_runtime_load_block_reason(
        skill,
        enabled_prebuilt_ids=set(),
        enabled_local_ids=set(),
    )
    assert reason == "disabled"


def test_filter_skills_for_runtime_load() -> None:
    active = _skill("active")
    archived = _skill("archived", lifecycle=SkillLifecycleStatus.ARCHIVED.value)
    allowed, blocked = filter_skills_for_runtime_load(
        [active, archived],
        enabled_prebuilt_ids=set(),
        enabled_local_ids={"active", "archived"},
    )
    assert [s.id for s in allowed] == ["active"]
    assert blocked == [("archived", "archived")]
