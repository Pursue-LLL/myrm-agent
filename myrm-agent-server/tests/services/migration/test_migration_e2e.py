"""End-to-end migration pipeline tests (discover payload → dry-run → confirm shape)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.memory.import_adapters import build_memory_import_dry_run
from app.services.migration.source_payload_loader import (
    extract_pending_skills,
    load_source_payload,
)
from app.services.migration.source_payload_split import (
    build_instruction_plan,
    extract_memory_payload,
)


@pytest.fixture()
def hermes_e2e_root(tmp_path: Path) -> Path:
    root = tmp_path / ".hermes"
    root.mkdir()
    (root / "SOUL.md").write_text("You are a precise assistant.", encoding="utf-8")
    memories = root / "memories"
    memories.mkdir()
    (memories / "MEMORY.md").write_text("- Prefers TypeScript\n- Works remotely", encoding="utf-8")
    (memories / "USER.md").write_text("- Name: Bob", encoding="utf-8")
    (root / ".env").write_text("OPENAI_API_KEY=sk-test-openai\n", encoding="utf-8")
    skill_dir = root / "skills" / "lint"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: lint\n---\nLint skill", encoding="utf-8")
    return root


@pytest.fixture()
def openclaw_e2e_root(tmp_path: Path) -> Path:
    root = tmp_path / ".openclaw"
    root.mkdir()
    (root / "sessions.json").write_text(
        json.dumps([{"title": "Sprint", "summary": "Shipped feature", "created_at": "2024-06-01T00:00:00Z"}]),
        encoding="utf-8",
    )
    (root / "memory.json").write_text(
        json.dumps([{"content": "User prefers concise answers"}]),
        encoding="utf-8",
    )
    workspace = root / "workspace-main"
    workspace.mkdir()
    (workspace / "MEMORY.md").write_text("- Workspace preference bullet", encoding="utf-8")
    (workspace / "SOUL.md").write_text("You are a concise assistant.", encoding="utf-8")
    return root


class TestMigrationE2E:
    def test_hermes_discover_to_dry_run(
        self,
        hermes_e2e_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        discovery = {"competitor": "hermes", "root": str(hermes_e2e_root), "files": []}
        loaded = load_source_payload(discovery)
        dry_run = build_memory_import_dry_run(loaded, "hermes")
        skills = extract_pending_skills(loaded)

        assert dry_run.summary.source == "hermes"
        assert dry_run.summary.mapped_items > 0
        assert dry_run.summary.status in {"ready", "warning"}
        assert len(skills) == 1
        assert loaded.get("env_keys")

    def test_hermes_split_excludes_soul_from_memory_dry_run(
        self,
        hermes_e2e_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_source_payload(
            {"competitor": "hermes", "root": str(hermes_e2e_root), "files": []},
        )
        plan = build_instruction_plan(loaded)
        memory_payload = extract_memory_payload(loaded, include_episodic=False)
        dry_run = build_memory_import_dry_run(memory_payload, "hermes")

        assert "precise assistant" in plan.agent_persona
        assert "soul_md" not in memory_payload
        buckets = {m.source_bucket for m in dry_run.mappings}
        assert "SOUL.md" not in buckets

    def test_openclaw_discover_to_dry_run(
        self,
        openclaw_e2e_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        discovery = {"competitor": "openclaw", "root": str(openclaw_e2e_root), "files": []}
        loaded = load_source_payload(discovery)
        dry_run = build_memory_import_dry_run(loaded, "openclaw")

        assert dry_run.summary.source == "openclaw"
        assert dry_run.summary.mapped_items > 0
        plan = build_instruction_plan(loaded)
        assert "concise assistant" in plan.agent_persona
        sessions = loaded.get("openclaw_sessions")
        assert isinstance(sessions, list)
        assert len(sessions) >= 1

    def test_openclaw_split_auto_keeps_sessions_in_openclaw_adapter(
        self,
        openclaw_e2e_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_source_payload(
            {"competitor": "openclaw", "root": str(openclaw_e2e_root), "files": []},
        )
        memory_payload = extract_memory_payload(loaded, include_episodic=True)
        dry_run = build_memory_import_dry_run(memory_payload, "openclaw")

        assert dry_run.summary.source == "openclaw"
        assert dry_run.summary.mapped_items >= 2
        buckets = {mapping.source_bucket for mapping in dry_run.mappings}
        assert "openclaw_sessions" in buckets

