"""Tests for competitor payload loader and end-to-end dry-run integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.memory.import_adapters import build_memory_import_dry_run
from app.services.migration.competitor_payload_loader import (
    is_competitor_discovery_payload,
    load_competitor_payload,
)


@pytest.fixture()
def hermes_fixture(tmp_path: Path) -> Path:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / "SOUL.md").write_text("I am a helpful assistant.", encoding="utf-8")
    memories = root / "memories"
    memories.mkdir()
    (memories / "MEMORY.md").write_text("- User prefers Python\n- Uses VS Code", encoding="utf-8")
    (memories / "USER.md").write_text("- Name: Alice", encoding="utf-8")
    skills = root / "skills" / "deploy"
    skills.mkdir(parents=True)
    (skills / "SKILL.md").write_text("---\nname: deploy\n---\nDeploy skill", encoding="utf-8")
    return root


@pytest.fixture()
def openclaw_fixture(tmp_path: Path) -> Path:
    root = tmp_path / ".openclaw"
    root.mkdir()
    (root / "sessions.json").write_text(
        json.dumps([{"title": "Debug", "summary": "Fixed auth", "created_at": "2024-01-01T00:00:00Z"}]),
        encoding="utf-8",
    )
    (root / "memory.json").write_text(
        json.dumps([{"content": "User prefers dark mode"}]),
        encoding="utf-8",
    )
    workspace = root / "workspace-main"
    workspace.mkdir()
    (workspace / "MEMORY.md").write_text("- Workspace memory bullet", encoding="utf-8")
    (workspace / "SOUL.md").write_text("Be direct.", encoding="utf-8")
    (workspace / "USER.md").write_text("- Role: engineer", encoding="utf-8")
    return root


class TestCompetitorPayloadLoader:
    def test_is_discovery_payload(self) -> None:
        assert is_competitor_discovery_payload({"competitor": "hermes", "root": "/tmp"})
        assert not is_competitor_discovery_payload({"soul_md": "hello"})

    def test_load_hermes(self, hermes_fixture: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.migration.competitor_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_competitor_payload(
            {"competitor": "hermes", "root": str(hermes_fixture), "files": []},
        )
        assert "soul_md" in loaded
        assert "memory_md" in loaded
        assert isinstance(loaded.get("skills"), list)
        assert len(loaded["skills"]) == 1

    def test_load_openclaw(self, openclaw_fixture: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.migration.competitor_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_competitor_payload(
            {"competitor": "openclaw", "root": str(openclaw_fixture), "files": []},
        )
        assert isinstance(loaded.get("openclaw_sessions"), list)
        assert "soul_md" in loaded
        assert "user_md" in loaded
        assert "memory_md" in loaded
        assert len(loaded["openclaw_sessions"]) == 1
        assert isinstance(loaded.get("openclaw_memory"), list)
        assert len(loaded["openclaw_memory"]) >= 2

    def test_load_openclaw_merges_workspace_markdown_into_memory(
        self,
        openclaw_fixture: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.competitor_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_competitor_payload(
            {"competitor": "openclaw", "root": str(openclaw_fixture), "files": []},
        )
        memory_entries = loaded.get("openclaw_memory")
        assert isinstance(memory_entries, list)
        contents = [
            str(entry.get("content", ""))
            for entry in memory_entries
            if isinstance(entry, dict)
        ]
        assert any("Workspace memory bullet" in item for item in contents)
        assert any("dark mode" in item for item in contents)

    def test_load_claude_skills_and_settings(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        root = tmp_path / ".claude"
        root.mkdir()
        (root / "CLAUDE.md").write_text("Project rules here.", encoding="utf-8")
        (root / "settings.json").write_text('{"model": "claude-sonnet"}', encoding="utf-8")
        skill_dir = root / "skills" / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: review\n---\nReview code", encoding="utf-8")

        monkeypatch.setattr(
            "app.services.migration.competitor_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_competitor_payload(
            {"competitor": "claude", "root": str(root), "files": []},
        )
        assert isinstance(loaded.get("semantic"), list)
        assert isinstance(loaded.get("claude_settings"), dict)
        skills = loaded.get("skills")
        assert isinstance(skills, list)
        assert len(skills) == 1

    def test_dry_run_from_discovery_payload(
        self,
        hermes_fixture: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.competitor_payload_loader.is_local_mode",
            lambda: True,
        )
        discovery_payload = {
            "competitor": "hermes",
            "root": str(hermes_fixture),
            "files": [],
        }
        loaded = load_competitor_payload(discovery_payload)
        result = build_memory_import_dry_run(loaded, "hermes")
        assert result.summary.source == "hermes"
        assert result.summary.mapped_items > 0
        assert result.summary.status in {"ready", "warning"}
