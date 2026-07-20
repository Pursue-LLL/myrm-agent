"""Integration: skill usage stats → curator sweep (no mock on key path).

Exercises real SkillStatsCollector, usage_recorder injection, LocalSkillBackend,
DefaultForgettingStrategy, and run_curator_sweep end-to-end.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.types import SkillLifecycleStatus
from myrm_agent_harness.backends.skills.usage_recorder import (
    flush_skill_usage_stats,
    get_injected_stats_collector,
    record_skill_selection,
    reset_turn_usage_dedupe,
    set_stats_collector,
)


@pytest.fixture
def curator_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated skills root + curator data dir; resets service singletons."""
    import app.core.skills.curator_service as curator_service
    import app.core.skills.models as models_mod

    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_root)])
    monkeypatch.setattr(curator_service, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_root)])
    monkeypatch.setattr(curator_service, "_get_data_dir", lambda: data_dir)

    curator_service._stats_collector = None
    curator_service._curator_config = None
    set_stats_collector(None)
    reset_turn_usage_dedupe()

    yield skills_root

    curator_service._stats_collector = None
    curator_service._curator_config = None
    set_stats_collector(None)


def _write_skill(skills_root: Path, name: str, *, stats: dict[str, object] | None = None) -> Path:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill {name}\n---\nBody.\n",
        encoding="utf-8",
    )
    if stats is not None:
        (skill_dir / ".stats.json").write_text(json.dumps(stats), encoding="utf-8")
    return skill_dir


@pytest.mark.integration
@pytest.mark.asyncio
async def test_curator_sweep_marks_inactive_skill_stale(curator_workspace: Path) -> None:
    """Long-inactive skill with usage history → stale on real sweep."""
    old = (datetime.now(UTC) - timedelta(days=60)).isoformat()
    _write_skill(
        curator_workspace,
        "inactive_integration_skill",
        stats={
            "call_count": 3,
            "success_count": 3,
            "failure_count": 0,
            "last_used_at": old,
            "created_at": old,
            "lifecycle_status": "active",
        },
    )

    from app.core.skills.curator_service import get_stats_collector, run_curator_sweep, update_curator_config

    update_curator_config({"stale_after_days": 30, "grace_period_days": 0, "enabled": True})
    collector = get_stats_collector()
    assert get_injected_stats_collector() is collector

    result = await run_curator_sweep(force=True, trigger="manual")
    assert result.skills_scanned >= 1
    assert result.stale_count >= 1

    stats_file = curator_workspace / "inactive_integration_skill" / ".stats.json"
    persisted = json.loads(stats_file.read_text())
    assert persisted["lifecycle_status"] == SkillLifecycleStatus.STALE


@pytest.mark.integration
@pytest.mark.asyncio
async def test_never_used_young_skill_not_stale(curator_workspace: Path) -> None:
    """Regression: never-used skill within stale_after_days must stay active."""
    recent = datetime.now(UTC).isoformat()
    _write_skill(
        curator_workspace,
        "young_never_used",
        stats={
            "call_count": 0,
            "success_count": 0,
            "failure_count": 0,
            "created_at": recent,
            "lifecycle_status": "active",
        },
    )

    from app.core.skills.curator_service import run_curator_sweep, update_curator_config

    update_curator_config({"stale_after_days": 30, "grace_period_days": 0, "enabled": True})
    result = await run_curator_sweep(force=True, trigger="manual")

    stats_file = curator_workspace / "young_never_used" / ".stats.json"
    persisted = json.loads(stats_file.read_text())
    assert persisted["lifecycle_status"] == SkillLifecycleStatus.ACTIVE
    assert result.stale_count == 0 or "young_never_used" not in {t.skill_name for t in result.transitions}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prebuilt_skill_exempt_from_sweep(curator_workspace: Path) -> None:
    """Prebuilt path skills must not be marked stale."""
    import app.core.skills.models as models_mod

    prebuilt_root = curator_workspace.parent / "assets" / "prebuilt" / "sys_skill"
    prebuilt_root.mkdir(parents=True)
    (prebuilt_root / "SKILL.md").write_text(
        "---\nname: sys_skill\ndescription: Prebuilt system skill\n---\nPrebuilt.\n",
        encoding="utf-8",
    )
    old = (datetime.now(UTC) - timedelta(days=200)).isoformat()
    (prebuilt_root / ".stats.json").write_text(
        json.dumps(
            {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "created_at": old,
                "lifecycle_status": "active",
            }
        ),
        encoding="utf-8",
    )

    paths = [str(curator_workspace), str(prebuilt_root.parent.parent)]
    import app.core.skills.curator_service as curator_service

    curator_service.DEFAULT_LOCAL_SKILL_PATHS = paths
    models_mod.DEFAULT_LOCAL_SKILL_PATHS = paths

    from app.core.skills.curator_service import run_curator_sweep, update_curator_config

    update_curator_config(
        {"stale_after_days": 7, "grace_period_days": 0, "protect_system_skills": True, "enabled": True}
    )
    await run_curator_sweep(force=True, trigger="manual")

    persisted = json.loads((prebuilt_root / ".stats.json").read_text())
    assert persisted["lifecycle_status"] == SkillLifecycleStatus.ACTIVE


@pytest.mark.integration
@pytest.mark.asyncio
async def test_usage_recorder_to_curator_via_api_client(curator_workspace: Path) -> None:
    """POST /curator/run after usage_recorder write — API layer, real sweep."""
    from datetime import UTC, datetime, timedelta

    from fastapi.testclient import TestClient

    from tests.api.skills.conftest import _load_curator_module

    skill_dir = _write_skill(curator_workspace, "api_pipeline_skill")
    old_date = datetime.now(UTC) - timedelta(days=45)

    from myrm_agent_harness.backends.skills.types import SkillMetadata

    from app.core.skills.curator_service import get_stats_collector, update_curator_config

    update_curator_config({"stale_after_days": 30, "grace_period_days": 0, "enabled": True})
    collector = get_stats_collector()
    reset_turn_usage_dedupe()
    record_skill_selection(
        SkillMetadata(name="api_pipeline_skill", description="API test", storage_path=str(skill_dir)),
        success=True,
    )
    flush_skill_usage_stats()

    stats = json.loads((skill_dir / ".stats.json").read_text())
    assert stats["call_count"] == 1

    # Age last_used_at on disk so sweep marks stale (recorder just wrote fresh timestamp)
    stats["last_used_at"] = old_date.isoformat()
    (skill_dir / ".stats.json").write_text(json.dumps(stats), encoding="utf-8")
    collector._pending_updates.clear()  # noqa: SLF001 — force reload from disk

    from fastapi import FastAPI

    app = FastAPI()
    curator_module = _load_curator_module()
    app.include_router(curator_module.router, prefix="/api/v1/skills")
    client = TestClient(app)

    response = client.post("/api/v1/skills/curator/run")
    assert response.status_code == 200
    body = response.json()
    assert body["skills_scanned"] >= 1

    persisted = json.loads((skill_dir / ".stats.json").read_text())
    assert persisted["lifecycle_status"] == SkillLifecycleStatus.STALE
