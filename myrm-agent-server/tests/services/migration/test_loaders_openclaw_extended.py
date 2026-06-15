"""Extended unit tests for OpenClaw loader branches in _loaders_openclaw.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.migration._loaders_openclaw import load_openclaw


class TestOpenClawConfigJson:
    def test_extracts_mcp_from_config_json(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        config = {"mcp_servers": {"github": {"command": "gh-mcp"}}}
        (root / "config.json").write_text(json.dumps(config), encoding="utf-8")

        result = load_openclaw(root, [])
        assert result["mcp_servers"] == {"github": {"command": "gh-mcp"}}
        assert result["openclaw_config"] == config

    def test_extracts_mcp_from_config_json_mcp_key(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        config = {"mcp": {"slack": {"command": "slack-srv"}}}
        (root / "config.json").write_text(json.dumps(config), encoding="utf-8")

        result = load_openclaw(root, [])
        assert result["mcp_servers"] == {"slack": {"command": "slack-srv"}}

    def test_no_mcp_when_config_empty(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        (root / "config.json").write_text(json.dumps({"theme": "dark"}), encoding="utf-8")

        result = load_openclaw(root, [])
        assert "mcp_servers" not in result
        assert result["openclaw_config"] == {"theme": "dark"}


class TestOpenClawConfigYaml:
    def test_extracts_mcp_from_config_yaml(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        (root / "config.yaml").write_text("mcp_servers:\n  fs:\n    command: fs-srv\n", encoding="utf-8")

        result = load_openclaw(root, [])
        assert result["mcp_servers"] == {"fs": {"command": "fs-srv"}}

    def test_config_yaml_as_hermes_config(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        (root / "config.yaml").write_text("model: claude-sonnet\n", encoding="utf-8")

        result = load_openclaw(root, [])
        assert result["hermes_config"] == {"model": "claude-sonnet"}


class TestOpenClawSkills:
    def test_loads_root_skills(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        skill_dir = root / "skills" / "deploy"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Deploy", encoding="utf-8")

        result = load_openclaw(root, [])
        skills = result.get("openclaw_skills")
        assert isinstance(skills, list)
        assert len(skills) == 1
        assert skills[0]["name"] == "deploy"

    def test_merges_workspace_skills(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        ws = root / "workspace-main"
        ws.mkdir()
        ws_skill = ws / "skills" / "test"
        ws_skill.mkdir(parents=True)
        (ws_skill / "SKILL.md").write_text("Test skill", encoding="utf-8")

        result = load_openclaw(root, [])
        skills = result.get("openclaw_skills")
        assert isinstance(skills, list)
        assert any(s["name"] == "test" for s in skills)


class TestOpenClawWorkspaceMd:
    def test_collects_soul_from_workspace(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        ws = root / "workspace"
        ws.mkdir()
        (ws / "SOUL.md").write_text("Be helpful.", encoding="utf-8")

        result = load_openclaw(root, [])
        assert "Be helpful." in str(result.get("soul_md"))

    def test_collects_user_from_workspace(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        ws = root / "workspace"
        ws.mkdir()
        (ws / "USER.md").write_text("- Prefers Python", encoding="utf-8")

        result = load_openclaw(root, [])
        assert "- Prefers Python" in str(result.get("user_md"))

    def test_joins_multiple_workspace_texts(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        ws1 = root / "workspace-main"
        ws1.mkdir()
        (ws1 / "SOUL.md").write_text("First.", encoding="utf-8")
        ws2 = root / "workspace-alt"
        ws2.mkdir()
        (ws2 / "SOUL.md").write_text("Second.", encoding="utf-8")

        result = load_openclaw(root, [])
        soul = result.get("soul_md")
        assert isinstance(soul, str)
        assert "First." in soul
        assert "Second." in soul


class TestOpenClawMemoryNormalize:
    def test_nested_memories_key(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        data = {"memories": [{"content": "nested"}]}
        (root / "memory.json").write_text(json.dumps(data), encoding="utf-8")

        result = load_openclaw(root, [])
        memory = result.get("openclaw_memory")
        assert isinstance(memory, list)
        assert any(m.get("content") == "nested" for m in memory)

    def test_empty_memory_returns_no_key(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        (root / "memory.json").write_text("[]", encoding="utf-8")

        result = load_openclaw(root, [])
        assert "openclaw_memory" not in result


class TestOpenClawFilePaths:
    def test_uses_file_paths_for_sessions(self, tmp_path: Path) -> None:
        root = tmp_path / ".openclaw"
        root.mkdir()
        sessions_file = tmp_path / "sessions.json"
        sessions_file.write_text(json.dumps([{"title": "Custom"}]), encoding="utf-8")

        result = load_openclaw(root, [str(sessions_file)])
        sessions = result.get("openclaw_sessions")
        assert isinstance(sessions, list)
        assert len(sessions) == 1
