"""A skill on disk with usage statistics, for tests that decide what to do with skills by how they were used.

[INPUT]
- myrm_agent_harness.backends.skills.types::SkillLifecycleStatus, SkillMetadata, SkillUsageStats (POS: the skill record the curator reads)

[OUTPUT]
- make_skill: a SkillMetadata with a storage path and usage statistics

[POS]
Pytest-only helper shared by the consolidation tests, so each test states the skill it needs (pinned, archived, how
often used) and not how a record is assembled.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus, SkillMetadata, SkillUsageStats


def make_skill(
    name: str,
    description: str = "Test skill",
    *,
    pinned: bool = False,
    status: str = SkillLifecycleStatus.ACTIVE,
    call_count: int = 5,
    storage_path: str | None = None,
) -> SkillMetadata:
    """A skill that lives on disk, was created thirty days ago and last ran five days ago."""
    return SkillMetadata(
        name=name,
        description=description,
        storage_path=storage_path or f"/tmp/skills/{name}",
        usage_stats=SkillUsageStats(
            call_count=call_count,
            success_count=call_count,
            lifecycle_status=status,
            pinned=pinned,
            last_used_at=datetime.now(UTC) - timedelta(days=5),
            created_at=datetime.now(UTC) - timedelta(days=30),
        ),
    )
