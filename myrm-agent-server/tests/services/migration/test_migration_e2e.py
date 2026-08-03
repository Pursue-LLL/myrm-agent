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


def _make_pi_session_jsonl(session_id: str, messages: list[dict[str, str]]) -> str:
    header = json.dumps({
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": "2025-07-01T12:00:00Z",
        "cwd": "/tmp/test-project",
    })
    lines = [header]
    for idx, msg in enumerate(messages):
        entry = json.dumps({
            "id": f"entry-{idx}",
            "type": "message",
            "timestamp": "2025-07-01T12:00:01Z",
            "parentId": None,
            "message": {"role": msg["role"], "content": msg["content"]},
        })
        lines.append(entry)
    return "\n".join(lines)


@pytest.fixture()
def pi_e2e_root(tmp_path: Path) -> Path:
    root = tmp_path / ".pi" / "agent"
    root.mkdir(parents=True)
    (root / "AGENTS.md").write_text("You are a senior backend engineer.", encoding="utf-8")
    (root / "settings.json").write_text(
        json.dumps({"defaultProvider": "anthropic", "defaultModel": "claude-4-sonnet"}),
        encoding="utf-8",
    )
    (root / "auth.json").write_text(
        json.dumps({"anthropic": {"token": "sk-ant-test"}, "openai": {"token": "sk-test"}}),
        encoding="utf-8",
    )
    sessions = root / "sessions"
    sessions.mkdir()
    (sessions / "s1.jsonl").write_text(
        _make_pi_session_jsonl("s1", [
            {"role": "user", "content": "Build a REST API with FastAPI"},
            {"role": "assistant", "content": "I'll create a FastAPI app with proper routing."},
        ]),
        encoding="utf-8",
    )
    (sessions / "s2.jsonl").write_text(
        _make_pi_session_jsonl("s2", [
            {"role": "user", "content": "Add database migrations with Alembic"},
            {"role": "assistant", "content": "Setting up Alembic for SQLAlchemy models."},
        ]),
        encoding="utf-8",
    )
    skill_dir = root / "skills" / "deploy"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("Deploy to production via SSH", encoding="utf-8")
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

    def test_pi_discover_to_dry_run(
        self,
        pi_e2e_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        discovery = {"competitor": "pi", "root": str(pi_e2e_root), "files": []}
        loaded = load_source_payload(discovery)
        assert loaded.get("_source") == "pi"
        assert loaded.get("agents_md") is not None
        assert loaded.get("pi_settings") is not None
        assert isinstance(loaded.get("env_keys"), list)
        assert len(loaded["env_keys"]) == 2

        skills = extract_pending_skills(loaded)
        assert len(skills) == 1
        assert skills[0]["name"] == "deploy"

        plan = build_instruction_plan(loaded)
        assert "senior backend engineer" in plan.agent_persona.lower()
        assert "pi settings" in plan.global_supplement.lower()

    def test_pi_split_sessions_to_episodic_memory(
        self,
        pi_e2e_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_source_payload(
            {"competitor": "pi", "root": str(pi_e2e_root), "files": []},
        )
        memory_payload = extract_memory_payload(loaded, include_episodic=True)
        assert "agents_md" not in memory_payload
        assert "pi_settings" not in memory_payload
        pi_sessions = memory_payload.get("pi_sessions")
        assert isinstance(pi_sessions, list) and len(pi_sessions) == 2

        dry_run = build_memory_import_dry_run(memory_payload)
        assert dry_run.summary.mapped_items == 2
        assert dry_run.summary.status == "ready"
        episodic = dry_run.normalized_data.get("episodic")
        assert isinstance(episodic, list) and len(episodic) == 2
        contents = [e["content"] for e in episodic]
        assert any("REST API" in c for c in contents)
        assert any("Alembic" in c for c in contents)

    def test_pi_episodic_disabled_strips_sessions(
        self,
        pi_e2e_root: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "app.services.migration.source_payload_loader.is_local_mode",
            lambda: True,
        )
        loaded = load_source_payload(
            {"competitor": "pi", "root": str(pi_e2e_root), "files": []},
        )
        memory_payload = extract_memory_payload(loaded, include_episodic=False)
        assert "pi_sessions" not in memory_payload

