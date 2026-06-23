"""Integration test: Hermes .usage.json → full pipeline → Harness StatsCollector reads.

Validates the end-to-end chain without mocking key paths:
  1. Hermes directory with skills + .usage.json
  2. load_source_payload() loads usage into skill payload
  3. extract_pending_skills() returns skills with usage_stats
  4. _apply_skill_migration() writes .stats.json
  5. Harness SkillStatsCollector._load_stats() reads and parses correctly
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.migration.source_payload_loader import (
    extract_pending_skills,
    load_source_payload,
)


@pytest.fixture()
def hermes_root_with_usage(tmp_path: Path) -> Path:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / "SOUL.md").write_text("You are a test assistant.", encoding="utf-8")

    skills_dir = root / "skills"
    skill_a = skills_dir / "code-review"
    skill_a.mkdir(parents=True)
    (skill_a / "SKILL.md").write_text("---\nname: code-review\n---\nReview code.", encoding="utf-8")

    skill_b = skills_dir / "deploy-helper"
    skill_b.mkdir(parents=True)
    (skill_b / "SKILL.md").write_text("---\nname: deploy-helper\n---\nDeploy helper.", encoding="utf-8")

    usage_data = {
        "code-review": {
            "use_count": 120,
            "last_used_at": "2026-06-22T18:30:00Z",
            "created_at": "2025-11-10T09:00:00Z",
            "state": "active",
            "pinned": True,
        },
        "deploy-helper": {
            "use_count": 7,
            "last_used_at": "2026-05-01T12:00:00Z",
            "created_at": "2026-04-01T08:00:00Z",
            "state": "stale",
            "pinned": False,
        },
    }
    (skills_dir / ".usage.json").write_text(json.dumps(usage_data), encoding="utf-8")
    return root


class TestUsageSidecarIntegration:
    """Full pipeline integration: discover → load → apply → harness read."""

    def test_load_source_payload_includes_usage_in_skills(
        self,
        hermes_root_with_usage: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        discovery = {
            "competitor": "hermes",
            "root": str(hermes_root_with_usage),
            "files": [],
        }
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        assert len(skills) == 2
        by_name = {s["name"]: s for s in skills}

        assert "usage_stats" in by_name["code-review"]
        assert by_name["code-review"]["usage_stats"]["use_count"] == 120
        assert by_name["code-review"]["usage_stats"]["pinned"] is True

        assert "usage_stats" in by_name["deploy-helper"]
        assert by_name["deploy-helper"]["usage_stats"]["state"] == "stale"

    @pytest.mark.asyncio
    async def test_apply_migration_writes_stats_readable_by_harness(
        self,
        hermes_root_with_usage: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        import app.core.skills.models as models_mod

        skills_dest = tmp_path / "skills_dest"
        skills_dest.mkdir()
        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_dest)])

        discovery = {
            "competitor": "hermes",
            "root": str(hermes_root_with_usage),
            "files": [],
        }
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        from app.api.skills.migrations import _apply_skill_migration

        result = await _apply_skill_migration(skills)

        assert result["skills_imported"] == 2
        assert result["usage_preserved"] == 2

        from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector

        collector = SkillStatsCollector(workspace_root=skills_dest)
        code_review_dir = skills_dest / "code-review"
        deploy_helper_dir = skills_dest / "deploy-helper"

        cr_stats = collector._load_stats(code_review_dir)
        assert cr_stats.call_count == 120
        assert cr_stats.success_count == 120
        assert cr_stats.pinned is True
        assert cr_stats.lifecycle_status == "active"
        assert cr_stats.last_used_at is not None
        assert "2026-06-22" in cr_stats.last_used_at.isoformat()
        assert cr_stats.created_at is not None
        assert "2025-11-10" in cr_stats.created_at.isoformat()

        dh_stats = collector._load_stats(deploy_helper_dir)
        assert dh_stats.call_count == 7
        assert dh_stats.lifecycle_status == "stale"
        assert dh_stats.pinned is False
        assert dh_stats.last_used_at is not None
        assert "2026-05-01" in dh_stats.last_used_at.isoformat()

    def test_no_usage_json_skills_still_load_without_stats(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Skills without .usage.json load normally — no usage_stats field."""
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        root = tmp_path / ".hermes"
        root.mkdir()
        skill_dir = root / "skills" / "basic"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: basic\n---\nBasic.", encoding="utf-8")

        discovery = {"competitor": "hermes", "root": str(root), "files": []}
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        assert len(skills) == 1
        assert "usage_stats" not in skills[0]

    @pytest.mark.asyncio
    async def test_partial_usage_only_matched_skills_get_stats(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When .usage.json has records for only some skills, unmatched skills get no .stats.json."""
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        import app.core.skills.models as models_mod

        root = tmp_path / ".hermes"
        root.mkdir()
        skills_dir = root / "skills"

        for name in ("tracked", "untracked"):
            d = skills_dir / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"---\nname: {name}\n---\n{name}.", encoding="utf-8")

        usage_data = {
            "tracked": {
                "use_count": 30,
                "last_used_at": "2026-06-20T10:00:00Z",
                "created_at": "2026-03-01T08:00:00Z",
                "state": "active",
                "pinned": False,
            },
        }
        (skills_dir / ".usage.json").write_text(json.dumps(usage_data), encoding="utf-8")

        skills_dest = tmp_path / "output"
        skills_dest.mkdir()
        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_dest)])

        discovery = {"competitor": "hermes", "root": str(root), "files": []}
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        from app.api.skills.migrations import _apply_skill_migration

        result = await _apply_skill_migration(skills)

        assert result["skills_imported"] == 2
        assert result["usage_preserved"] == 1

        tracked_stats = skills_dest / "tracked" / ".stats.json"
        untracked_stats = skills_dest / "untracked" / ".stats.json"
        assert tracked_stats.exists()
        assert not untracked_stats.exists()

        stats_data = json.loads(tracked_stats.read_text())
        assert stats_data["call_count"] == 30

    @pytest.mark.asyncio
    async def test_migrated_skill_not_marked_stale_by_curator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Core bug fix validation: skill with usage history must NOT be stale-flagged by Curator."""
        import app.core.skills.models as models_mod

        root = tmp_path / ".hermes"
        root.mkdir()
        skills_dir = root / "skills"
        skill_d = skills_dir / "production-deploy"
        skill_d.mkdir(parents=True)
        (skill_d / "SKILL.md").write_text("---\nname: production-deploy\n---\nDeploy.", encoding="utf-8")
        usage_data = {
            "production-deploy": {
                "use_count": 50,
                "last_used_at": "2026-06-20T10:00:00Z",
                "created_at": "2025-06-01T08:00:00Z",
                "state": "active",
                "pinned": False,
            },
        }
        (skills_dir / ".usage.json").write_text(json.dumps(usage_data), encoding="utf-8")

        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        skills_dest = tmp_path / "dest"
        skills_dest.mkdir()
        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_dest)])

        discovery = {"competitor": "hermes", "root": str(root), "files": []}
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        from app.api.skills.migrations import _apply_skill_migration

        await _apply_skill_migration(skills)

        from myrm_agent_harness.backends.skills.forgetting_strategy import (
            CuratorConfig,
            DefaultForgettingStrategy,
        )
        from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
        from myrm_agent_harness.backends.skills.types import SkillMetadata

        collector = SkillStatsCollector(workspace_root=skills_dest)
        stats = collector._load_stats(skills_dest / "production-deploy")

        assert stats.call_count == 50
        assert stats.last_used_at is not None

        strategy = DefaultForgettingStrategy(CuratorConfig())
        skill_meta = SkillMetadata(
            name="production-deploy",
            description="Deploy.",
            usage_stats=stats,
        )
        reason = strategy.should_forget(skill_meta)
        assert reason is None, f"Curator should NOT flag migrated skill as stale, got: {reason}"

    @pytest.mark.asyncio
    async def test_use_count_nonzero_but_no_last_used_at_not_stale(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Edge: use_count > 0 but last_used_at absent → must not be flagged stale."""
        import app.core.skills.models as models_mod

        root = tmp_path / ".hermes"
        root.mkdir()
        skills_dir = root / "skills"
        sd = skills_dir / "edge-skill"
        sd.mkdir(parents=True)
        (sd / "SKILL.md").write_text("---\nname: edge-skill\n---\nEdge.", encoding="utf-8")
        usage_data = {
            "edge-skill": {
                "use_count": 15,
                "created_at": "2025-01-01T00:00:00Z",
                "state": "active",
                "pinned": False,
            },
        }
        (skills_dir / ".usage.json").write_text(json.dumps(usage_data), encoding="utf-8")

        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        skills_dest = tmp_path / "dest2"
        skills_dest.mkdir()
        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_dest)])

        discovery = {"competitor": "hermes", "root": str(root), "files": []}
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        from app.api.skills.migrations import _apply_skill_migration

        await _apply_skill_migration(skills)

        from myrm_agent_harness.backends.skills.forgetting_strategy import (
            CuratorConfig,
            DefaultForgettingStrategy,
        )
        from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
        from myrm_agent_harness.backends.skills.types import SkillMetadata

        collector = SkillStatsCollector(workspace_root=skills_dest)
        stats = collector._load_stats(skills_dest / "edge-skill")

        assert stats.call_count == 15
        assert stats.last_used_at is None

        strategy = DefaultForgettingStrategy(CuratorConfig())
        skill_meta = SkillMetadata(
            name="edge-skill",
            description="Edge.",
            usage_stats=stats,
        )
        reason = strategy.should_forget(skill_meta)
        assert reason is None, f"call_count > 0 with no last_used should NOT trigger stale: {reason}"

    @pytest.mark.asyncio
    async def test_pinned_skill_always_exempt_from_curator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Pinned skills from Hermes must be exempt from all Curator transitions."""
        import app.core.skills.models as models_mod

        root = tmp_path / ".hermes"
        root.mkdir()
        skills_dir = root / "skills"
        sd = skills_dir / "pinned-skill"
        sd.mkdir(parents=True)
        (sd / "SKILL.md").write_text("---\nname: pinned-skill\n---\nPinned.", encoding="utf-8")
        usage_data = {
            "pinned-skill": {
                "use_count": 2,
                "last_used_at": "2025-01-01T00:00:00Z",
                "created_at": "2024-01-01T00:00:00Z",
                "state": "active",
                "pinned": True,
            },
        }
        (skills_dir / ".usage.json").write_text(json.dumps(usage_data), encoding="utf-8")

        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        skills_dest = tmp_path / "dest3"
        skills_dest.mkdir()
        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_dest)])

        discovery = {"competitor": "hermes", "root": str(root), "files": []}
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        from app.api.skills.migrations import _apply_skill_migration

        await _apply_skill_migration(skills)

        from myrm_agent_harness.backends.skills.forgetting_strategy import (
            CuratorConfig,
            DefaultForgettingStrategy,
        )
        from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector
        from myrm_agent_harness.backends.skills.types import SkillMetadata

        collector = SkillStatsCollector(workspace_root=skills_dest)
        stats = collector._load_stats(skills_dest / "pinned-skill")

        assert stats.pinned is True

        strategy = DefaultForgettingStrategy(CuratorConfig())
        skill_meta = SkillMetadata(
            name="pinned-skill",
            description="Pinned.",
            usage_stats=stats,
        )
        reason = strategy.should_forget(skill_meta)
        assert reason is None, "Pinned skill must be immune to all curator transitions"

    def test_usage_json_as_array_returns_empty(self, tmp_path: Path) -> None:
        """Edge: .usage.json is a JSON array instead of object → graceful empty."""
        from app.services.migration._loader_utils import load_usage_sidecar

        (tmp_path / ".usage.json").write_text('[{"use_count": 5}]', encoding="utf-8")
        result = load_usage_sidecar(tmp_path)
        assert result == {}

    @pytest.mark.asyncio
    async def test_large_use_count_handled_correctly(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Edge: very large use_count value is preserved correctly."""
        import app.core.skills.models as models_mod

        root = tmp_path / ".hermes"
        root.mkdir()
        skills_dir = root / "skills"
        sd = skills_dir / "heavy-usage"
        sd.mkdir(parents=True)
        (sd / "SKILL.md").write_text("---\nname: heavy-usage\n---\nHeavy.", encoding="utf-8")
        usage_data = {
            "heavy-usage": {
                "use_count": 999999,
                "last_used_at": "2026-06-22T23:59:59Z",
                "created_at": "2024-01-01T00:00:00Z",
                "state": "active",
                "pinned": False,
            },
        }
        (skills_dir / ".usage.json").write_text(json.dumps(usage_data), encoding="utf-8")

        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        skills_dest = tmp_path / "dest4"
        skills_dest.mkdir()
        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(skills_dest)])

        discovery = {"competitor": "hermes", "root": str(root), "files": []}
        loaded = load_source_payload(discovery)
        skills = extract_pending_skills(loaded)

        from app.api.skills.migrations import _apply_skill_migration

        await _apply_skill_migration(skills)

        from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector

        collector = SkillStatsCollector(workspace_root=skills_dest)
        stats = collector._load_stats(skills_dest / "heavy-usage")
        assert stats.call_count == 999999
        assert stats.success_count == 999999
