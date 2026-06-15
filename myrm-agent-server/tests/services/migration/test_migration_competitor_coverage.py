"""Gap-fill tests for four-source competitor migration (v1.4 routing + lanes)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.memory.import_adapters import (
    build_memory_import_dry_run,
    resolve_competitor_import_source,
)
from app.services.migration.competitor_payload_loader import load_competitor_payload
from app.services.migration.competitor_payload_split import (
    build_instruction_plan,
    extract_memory_payload,
)


@pytest.fixture()
def _local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.migration.competitor_payload_loader.is_local_mode",
        lambda: True,
    )


class TestResolveCompetitorImportSource:
    @pytest.mark.parametrize(
        ("competitor", "expected"),
        [
            ("hermes", "hermes"),
            ("openclaw", "openclaw"),
            ("codex", "codex"),
            ("claude", "claude"),
            ("unknown_vendor", "auto"),
        ],
    )
    def test_maps_discovery_ids(self, competitor: str, expected: str) -> None:
        assert resolve_competitor_import_source(competitor) == expected


class TestAutoRoutingRegression:
    """v1.4: OpenClaw with soul_md must not mis-route to Hermes when source=auto."""

    def test_discovery_auto_openclaw_not_hermes(
        self,
        tmp_path: Path,
        _local: None,
    ) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        (root / "sessions.json").write_text("[]", encoding="utf-8")
        workspace = root / "workspace-main"
        workspace.mkdir()
        (workspace / "SOUL.md").write_text("Concise assistant.", encoding="utf-8")
        (workspace / "MEMORY.md").write_text("- Shared markdown fact", encoding="utf-8")

        discovery = {"competitor": "openclaw", "root": str(root), "files": []}
        loaded = load_competitor_payload(discovery)
        result = build_memory_import_dry_run(loaded, "auto")

        assert result.summary.source == "openclaw"
        assert "unsupported_source" not in result.warnings

    def test_discovery_auto_claude_explicit_adapter(
        self,
        tmp_path: Path,
        _local: None,
    ) -> None:
        root = tmp_path / ".claude"
        root.mkdir()
        (root / "CLAUDE.md").write_text("Run tests before merge.", encoding="utf-8")
        skill = root / "skills" / "lint"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: lint\n---\nLint", encoding="utf-8")

        loaded = load_competitor_payload(
            {"competitor": "claude", "root": str(root), "files": []},
        )
        memory_lane = extract_memory_payload(loaded, include_episodic=False)
        result = build_memory_import_dry_run(memory_lane, "claude")

        assert result.summary.source == "claude"
        assert result.summary.status == "ready"
        assert result.summary.mapped_items == 0
        plan = build_instruction_plan(loaded)
        assert "merge" in plan.agent_persona.lower() or plan.agent_persona.strip()


class TestOpenClawMultiWorkspace:
    def test_merges_memory_from_secondary_workspace(
        self,
        tmp_path: Path,
        _local: None,
    ) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        (root / "sessions.json").write_text("[]", encoding="utf-8")
        main = root / "workspace-main"
        main.mkdir()
        (main / "MEMORY.md").write_text("- Main fact", encoding="utf-8")
        alt = root / "workspace-side"
        alt.mkdir()
        (alt / "MEMORY.md").write_text("- Side project fact", encoding="utf-8")

        loaded = load_competitor_payload(
            {"competitor": "openclaw", "root": str(root), "files": []},
        )
        entries = loaded.get("openclaw_memory")
        assert isinstance(entries, list)
        contents = [str(item.get("content", "")) for item in entries if isinstance(item, dict)]
        assert any("Main fact" in text for text in contents)
        assert any("Side project fact" in text for text in contents)

    def test_sessions_json_episodic_preserved(
        self,
        tmp_path: Path,
        _local: None,
    ) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        (root / "sessions.json").write_text(
            json.dumps([{"title": "Ship", "summary": "Released v1", "created_at": "2024-06-01T00:00:00Z"}]),
            encoding="utf-8",
        )
        (root / "workspace-main").mkdir()

        loaded = load_competitor_payload(
            {"competitor": "openclaw", "root": str(root), "files": []},
        )
        sessions = loaded.get("openclaw_sessions")
        assert isinstance(sessions, list)
        assert len(sessions) == 1


