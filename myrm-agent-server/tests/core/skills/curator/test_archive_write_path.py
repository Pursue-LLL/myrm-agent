"""apply_skill_archived: lifecycle state plus the config-version bump warm chats depend on."""

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus

from app.core.skills.config_version import get_skill_config_version
from app.core.skills.curator.service import SkillPinnedError, apply_skill_archived


@pytest.fixture
def skill_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path / "data"))
    directory = tmp_path / "skills" / "weekly-report"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("---\nname: weekly-report\ndescription: demo\n---\n", encoding="utf-8")
    return directory


def test_archive_and_restore_bump_the_config_version(skill_dir: Path) -> None:
    collector = SkillStatsCollector()
    assert get_skill_config_version() == 0.0

    assert apply_skill_archived(collector, skill_dir, archived=True) == SkillLifecycleStatus.ARCHIVED
    archived_version = get_skill_config_version()
    assert archived_version > 0.0
    assert collector.get_stats(skill_dir).lifecycle_status == SkillLifecycleStatus.ARCHIVED

    assert apply_skill_archived(collector, skill_dir, archived=False) == SkillLifecycleStatus.ACTIVE
    assert get_skill_config_version() >= archived_version
    assert collector.get_stats(skill_dir).lifecycle_status == SkillLifecycleStatus.ACTIVE


def test_refused_archive_does_not_bump_the_config_version(skill_dir: Path) -> None:
    collector = SkillStatsCollector()
    collector.set_pinned(skill_dir, pinned=True)

    with pytest.raises(SkillPinnedError):
        apply_skill_archived(collector, skill_dir, archived=True)

    assert get_skill_config_version() == 0.0
    assert collector.get_stats(skill_dir).lifecycle_status != SkillLifecycleStatus.ARCHIVED
