"""Tests for Hermes .usage.json sidecar import during skill migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.migration._loader_utils import load_usage_sidecar


class TestLoadUsageSidecar:
    def test_reads_valid_usage_json(self, tmp_path: Path) -> None:
        usage_data = {
            "blog-writing": {
                "use_count": 42,
                "last_used_at": "2026-06-20T10:00:00Z",
                "created_at": "2026-01-15T08:00:00Z",
                "state": "active",
                "pinned": False,
            },
            "axolotl-finetuning": {
                "use_count": 87,
                "last_used_at": "2026-06-22T15:30:00Z",
                "created_at": "2025-12-01T09:00:00Z",
                "state": "active",
                "pinned": True,
            },
        }
        usage_file = tmp_path / ".usage.json"
        usage_file.write_text(json.dumps(usage_data))

        result = load_usage_sidecar(tmp_path)

        assert len(result) == 2
        assert result["blog-writing"]["use_count"] == 42
        assert result["axolotl-finetuning"]["pinned"] is True

    def test_returns_empty_on_missing_file(self, tmp_path: Path) -> None:
        result = load_usage_sidecar(tmp_path)
        assert result == {}

    def test_returns_empty_on_corrupt_json(self, tmp_path: Path) -> None:
        usage_file = tmp_path / ".usage.json"
        usage_file.write_text("not valid json {{{")

        result = load_usage_sidecar(tmp_path)
        assert result == {}

    def test_filters_non_dict_values(self, tmp_path: Path) -> None:
        usage_data = {
            "valid-skill": {"use_count": 10, "state": "active"},
            "invalid-entry": "not a dict",
            "another-invalid": 123,
        }
        usage_file = tmp_path / ".usage.json"
        usage_file.write_text(json.dumps(usage_data))

        result = load_usage_sidecar(tmp_path)
        assert len(result) == 1
        assert "valid-skill" in result


class TestBuildStatsJson:
    """Test the Hermes→Myrm usage stats mapping in migrations.py."""

    def test_maps_hermes_fields_to_myrm_format(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        hermes_record = {
            "use_count": 42,
            "last_used_at": "2026-06-20T10:00:00Z",
            "created_at": "2026-01-15T08:00:00Z",
            "state": "active",
            "pinned": True,
        }

        result = _build_stats_json(hermes_record)

        assert result is not None
        assert result["call_count"] == 42
        assert result["success_count"] == 42
        assert result["failure_count"] == 0
        assert result["last_used_at"] == "2026-06-20T10:00:00Z"
        assert result["created_at"] == "2026-01-15T08:00:00Z"
        assert result["lifecycle_status"] == "active"
        assert result["pinned"] is True
        assert result["merged_into"] is None

    def test_maps_stale_state(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        result = _build_stats_json({"use_count": 5, "state": "stale", "created_at": "2026-01-01T00:00:00Z"})

        assert result is not None
        assert result["lifecycle_status"] == "stale"

    def test_returns_none_for_empty_usage(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        result = _build_stats_json({"use_count": 0})
        assert result is None

    def test_handles_missing_fields_gracefully(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        result = _build_stats_json({"use_count": 10})

        assert result is not None
        assert result["call_count"] == 10
        assert result["last_used_at"] is None
        assert result["created_at"] is None
        assert result["lifecycle_status"] == "active"
        assert result["pinned"] is False

    def test_coerces_string_use_count(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        result = _build_stats_json({"use_count": "42", "created_at": "2026-01-01T00:00:00Z"})

        assert result is not None
        assert result["call_count"] == 42

    def test_falls_back_to_zero_on_invalid_use_count(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        result = _build_stats_json({"use_count": "abc", "created_at": "2026-01-01T00:00:00Z"})

        assert result is not None
        assert result["call_count"] == 0

    def test_maps_archived_state(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        result = _build_stats_json({"use_count": 3, "state": "archived", "created_at": "2026-01-01T00:00:00Z"})

        assert result is not None
        assert result["lifecycle_status"] == "archived"

    def test_unknown_state_defaults_to_active(self) -> None:
        from app.api.skills.migrations import _build_stats_json

        result = _build_stats_json({"use_count": 3, "state": "unknown_state", "created_at": "2026-01-01T00:00:00Z"})

        assert result is not None
        assert result["lifecycle_status"] == "active"


class TestApplySkillMigrationWithUsage:
    """Integration test: verify .stats.json is written during skill migration."""

    @pytest.mark.asyncio
    async def test_writes_stats_json_when_usage_present(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.core.skills.models as models_mod

        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)])

        from app.api.skills.migrations import _apply_skill_migration

        skills_raw = [
            {
                "name": "test-skill",
                "content": "---\nname: test-skill\n---\nA test skill.",
                "usage_stats": {
                    "use_count": 55,
                    "last_used_at": "2026-06-21T12:00:00Z",
                    "created_at": "2026-03-10T08:00:00Z",
                    "state": "active",
                    "pinned": False,
                },
            },
        ]

        result = await _apply_skill_migration(skills_raw)

        assert result["skills_imported"] == 1
        assert result["usage_preserved"] == 1

        stats_file = tmp_path / "test-skill" / ".stats.json"
        assert stats_file.exists()

        stats_data = json.loads(stats_file.read_text())
        assert stats_data["call_count"] == 55
        assert stats_data["last_used_at"] == "2026-06-21T12:00:00Z"
        assert stats_data["created_at"] == "2026-03-10T08:00:00Z"
        assert stats_data["lifecycle_status"] == "active"

    @pytest.mark.asyncio
    async def test_no_stats_json_when_no_usage(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import app.core.skills.models as models_mod

        monkeypatch.setattr(models_mod, "DEFAULT_LOCAL_SKILL_PATHS", [str(tmp_path)])

        from app.api.skills.migrations import _apply_skill_migration

        skills_raw = [
            {
                "name": "no-usage-skill",
                "content": "---\nname: no-usage-skill\n---\nSkill without usage.",
            },
        ]

        result = await _apply_skill_migration(skills_raw)

        assert result["skills_imported"] == 1
        assert "usage_preserved" not in result

        stats_file = tmp_path / "no-usage-skill" / ".stats.json"
        assert not stats_file.exists()
