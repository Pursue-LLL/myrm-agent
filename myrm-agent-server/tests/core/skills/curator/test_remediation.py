"""Doctor remediation acts on the real per-skill ledger (no mocked collector)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus
from myrm_agent_harness.backends.skills.usage_recorder import set_stats_collector

import app.core.skills.curator.service as curator_service
from app.core.skills.curator.service import remediate_skill_finding


@pytest.fixture
def skills_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(curator_service, "DEFAULT_LOCAL_SKILL_PATHS", [str(root)])
    curator_service._stats_collector = None
    yield root
    curator_service._stats_collector = None
    set_stats_collector(None)


def _write_skill(root: Path, name: str, *, pinned: bool = False) -> Path:
    skill_dir = root / name
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Skill {name}\n---\nBody.\n", encoding="utf-8")
    used_at = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    ledger = {
        "call_count": 9,
        "success_count": 1,
        "failure_count": 8,
        "last_used_at": used_at,
        "created_at": used_at,
        "lifecycle_status": "active",
        "pinned": pinned,
        "usage_history": [{"timestamp": used_at, "success": False, "duration_ms": 0.0}],
    }
    (skill_dir / ".stats.json").write_text(json.dumps(ledger), encoding="utf-8")
    return skill_dir


def _ledger(skill_dir: Path) -> dict[str, object]:
    return json.loads((skill_dir / ".stats.json").read_text(encoding="utf-8"))


async def test_reset_stats_clears_counters_and_keeps_pin_and_lifecycle(skills_root: Path) -> None:
    skill_dir = _write_skill(skills_root, "flaky-scraper", pinned=True)

    result = await remediate_skill_finding("flaky-scraper", "reset_stats")

    assert result["success"] is True
    assert result["call_count"] == 0
    ledger = _ledger(skill_dir)
    assert (ledger["call_count"], ledger["success_count"], ledger["failure_count"]) == (0, 0, 0)
    assert ledger["usage_history"] == []
    assert ledger["pinned"] is True
    assert ledger["lifecycle_status"] == SkillLifecycleStatus.ACTIVE


async def test_archive_marks_an_unpinned_skill_archived(skills_root: Path) -> None:
    skill_dir = _write_skill(skills_root, "flaky-scraper")

    result = await remediate_skill_finding("flaky-scraper", "archive")

    assert result["success"] is True
    assert result["new_status"] == "archived"
    assert _ledger(skill_dir)["lifecycle_status"] == SkillLifecycleStatus.ARCHIVED


async def test_archive_refuses_a_pinned_skill(skills_root: Path) -> None:
    skill_dir = _write_skill(skills_root, "flaky-scraper", pinned=True)

    result = await remediate_skill_finding("flaky-scraper", "archive")

    assert result["success"] is False
    assert "pinned" in str(result["error"])
    assert _ledger(skill_dir)["lifecycle_status"] == SkillLifecycleStatus.ACTIVE


async def test_unpin_and_archive_releases_the_pin_then_archives(skills_root: Path) -> None:
    skill_dir = _write_skill(skills_root, "flaky-scraper", pinned=True)

    result = await remediate_skill_finding("flaky-scraper", "unpin_and_archive")

    assert result["success"] is True
    assert result["pinned"] is False
    ledger = _ledger(skill_dir)
    assert ledger["pinned"] is False
    assert ledger["lifecycle_status"] == SkillLifecycleStatus.ARCHIVED


@pytest.mark.parametrize("skill_name", ["missing-skill", "../escape"])
async def test_unknown_skill_is_rejected(skills_root: Path, skill_name: str) -> None:
    result = await remediate_skill_finding(skill_name, "archive")

    assert result["success"] is False


async def test_unsupported_action_is_rejected_without_touching_the_ledger(skills_root: Path) -> None:
    skill_dir = _write_skill(skills_root, "flaky-scraper")
    before = _ledger(skill_dir)

    result = await remediate_skill_finding("flaky-scraper", "delete_everything")

    assert result["success"] is False
    assert _ledger(skill_dir) == before
