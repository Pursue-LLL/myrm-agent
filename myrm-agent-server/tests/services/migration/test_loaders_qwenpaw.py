"""Unit tests for QwenPaw/CoPaw loader in _loaders_openclaw_qwenpaw.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.migration._loaders_openclaw_qwenpaw import load_qwenpaw
from app.services.migration.competitor_payload_loader import (
    build_coverage_items,
    load_competitor_payload,
)


@pytest.fixture()
def _local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.migration.competitor_payload_loader.is_local_mode",
        lambda: True,
    )


def _make_agent_json(
    workspace_dir: Path,
    *,
    name: str = "test-agent",
    agent_id: str = "agent-001",
    prompt_files: list[str] | None = None,
    mcp_clients: dict[str, object] | None = None,
) -> None:
    """Helper to create a valid agent.json in workspace_dir."""
    data: dict[str, object] = {"name": name, "id": agent_id}
    if prompt_files is not None:
        data["system_prompt_files"] = prompt_files
    if mcp_clients is not None:
        data["mcp"] = {"clients": mcp_clients}
    (workspace_dir / "agent.json").write_text(json.dumps(data), encoding="utf-8")


class TestLoadQwenpawBasic:
    def test_loads_single_agent(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "project-alpha"
        ws.mkdir()
        _make_agent_json(ws, name="Alpha", agent_id="alpha-1")

        result = load_qwenpaw(root, [])
        agents = result.get("qwenpaw_agents")
        assert isinstance(agents, list)
        assert len(agents) == 1
        assert agents[0]["name"] == "Alpha"
        assert agents[0]["id"] == "alpha-1"

    def test_loads_multiple_agents(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        for i in range(3):
            ws = root / f"workspace-{i}"
            ws.mkdir()
            _make_agent_json(ws, name=f"Agent-{i}", agent_id=f"id-{i}")

        result = load_qwenpaw(root, [])
        agents = result["qwenpaw_agents"]
        assert isinstance(agents, list)
        assert len(agents) == 3

    def test_skips_dirs_without_agent_json(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        (root / "empty-ws").mkdir()
        ws = root / "valid-ws"
        ws.mkdir()
        _make_agent_json(ws, name="Valid")

        result = load_qwenpaw(root, [])
        agents = result["qwenpaw_agents"]
        assert isinstance(agents, list)
        assert len(agents) == 1

    def test_empty_root_returns_empty_dict(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        result = load_qwenpaw(root, [])
        assert result == {}


class TestLoadQwenpawPrompts:
    def test_extracts_system_prompts(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        (ws / "prompt.md").write_text("You are a helpful assistant.", encoding="utf-8")
        _make_agent_json(ws, prompt_files=["prompt.md"])

        result = load_qwenpaw(root, [])
        agents = result["qwenpaw_agents"]
        assert isinstance(agents, list)
        assert agents[0]["system_prompt"] == "You are a helpful assistant."
        assert result["soul_md"] == "You are a helpful assistant."

    def test_joins_multiple_prompt_files(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        (ws / "base.md").write_text("Base personality.", encoding="utf-8")
        (ws / "tools.md").write_text("Use tools wisely.", encoding="utf-8")
        _make_agent_json(ws, prompt_files=["base.md", "tools.md"])

        result = load_qwenpaw(root, [])
        prompt = result["qwenpaw_agents"][0]["system_prompt"]
        assert isinstance(prompt, str)
        assert "Base personality." in prompt
        assert "Use tools wisely." in prompt
        assert "\n\n---\n\n" in prompt

    def test_missing_prompt_file_skipped(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws, prompt_files=["nonexistent.md"])

        result = load_qwenpaw(root, [])
        agents = result["qwenpaw_agents"]
        assert isinstance(agents, list)
        assert "system_prompt" not in agents[0]


class TestLoadQwenpawMcp:
    def test_extracts_mcp_clients(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        mcp = {
            "github": {"command": "npx", "args": ["@github/mcp-server"]},
            "filesystem": {"command": "npx", "args": ["@modelcontextprotocol/server-filesystem"]},
        }
        _make_agent_json(ws, mcp_clients=mcp)

        result = load_qwenpaw(root, [])
        mcp_servers = result.get("mcp_servers")
        assert isinstance(mcp_servers, dict)
        assert "github" in mcp_servers
        assert "filesystem" in mcp_servers
        assert mcp_servers["github"]["command"] == "npx"

    def test_merges_mcp_from_multiple_workspaces(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws1 = root / "ws1"
        ws1.mkdir()
        _make_agent_json(ws1, mcp_clients={"github": {"command": "gh"}})
        ws2 = root / "ws2"
        ws2.mkdir()
        _make_agent_json(ws2, name="Agent2", agent_id="id-2", mcp_clients={"slack": {"command": "slack-mcp"}})

        result = load_qwenpaw(root, [])
        mcp_servers = result["mcp_servers"]
        assert isinstance(mcp_servers, dict)
        assert "github" in mcp_servers
        assert "slack" in mcp_servers

    def test_no_mcp_when_absent(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)

        result = load_qwenpaw(root, [])
        assert "mcp_servers" not in result


class TestLoadQwenpawMemory:
    def test_loads_json_memory(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)
        mem_dir = root / "memory"
        mem_dir.mkdir()
        (mem_dir / "facts.json").write_text(
            json.dumps([{"content": "User prefers dark mode"}]),
            encoding="utf-8",
        )

        result = load_qwenpaw(root, [])
        memory = result.get("openclaw_memory")
        assert isinstance(memory, list)
        assert len(memory) == 1
        assert memory[0]["content"] == "User prefers dark mode"

    def test_loads_markdown_memory(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)
        mem_dir = root / "memory"
        mem_dir.mkdir()
        (mem_dir / "notes.md").write_text("- Fact one\n- Fact two", encoding="utf-8")

        result = load_qwenpaw(root, [])
        memory = result["openclaw_memory"]
        assert isinstance(memory, list)
        assert len(memory) == 2
        contents = [m["content"] for m in memory]
        assert "Fact one" in contents
        assert "Fact two" in contents


class TestLoadQwenpawSecrets:
    def test_extracts_env_keys(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)
        secret = root / ".secret"
        secret.mkdir()
        (secret / ".env").write_text("OPENAI_API_KEY=sk-test123\nDEEPSEEK_API_KEY=dk-xxx\n", encoding="utf-8")

        result = load_qwenpaw(root, [])
        env_keys = result.get("env_keys")
        assert isinstance(env_keys, list)
        names = [k["name"] for k in env_keys]
        assert "OPENAI_API_KEY" in names
        assert "DEEPSEEK_API_KEY" in names

    def test_no_secret_dir_means_no_keys(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)

        result = load_qwenpaw(root, [])
        assert "env_keys" not in result


class TestLoadQwenpawPlugins:
    def test_loads_plugins_as_skills(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)
        plugin = root / "plugins" / "web-search"
        plugin.mkdir(parents=True)
        (plugin / "SKILL.md").write_text("Web search plugin", encoding="utf-8")

        result = load_qwenpaw(root, [])
        skills = result.get("skills")
        assert isinstance(skills, list)
        assert len(skills) == 1
        assert skills[0]["name"] == "web-search"
        assert skills[0]["source"] == "qwenpaw"


class TestLoadQwenpawEdgeCases:
    """Edge cases and boundary conditions."""

    def test_agent_json_not_dict_skipped(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        (ws / "agent.json").write_text("[1, 2, 3]", encoding="utf-8")

        result = load_qwenpaw(root, [])
        assert result == {}

    def test_agent_json_invalid_json_skipped(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        (ws / "agent.json").write_text("{invalid json!!!", encoding="utf-8")

        result = load_qwenpaw(root, [])
        assert result == {}

    def test_mcp_field_not_dict_ignored(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        data = {"name": "Agent", "id": "a1", "mcp": "not a dict"}
        (ws / "agent.json").write_text(json.dumps(data), encoding="utf-8")

        result = load_qwenpaw(root, [])
        assert "mcp_servers" not in result
        assert len(result["qwenpaw_agents"]) == 1

    def test_mcp_clients_not_dict_ignored(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        data = {"name": "Agent", "id": "a1", "mcp": {"clients": ["not", "a", "dict"]}}
        (ws / "agent.json").write_text(json.dumps(data), encoding="utf-8")

        result = load_qwenpaw(root, [])
        assert "mcp_servers" not in result

    def test_system_prompt_files_not_list_ignored(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        data = {"name": "Agent", "id": "a1", "system_prompt_files": "not_a_list.md"}
        (ws / "agent.json").write_text(json.dumps(data), encoding="utf-8")

        result = load_qwenpaw(root, [])
        assert "system_prompt" not in result["qwenpaw_agents"][0]

    def test_memory_json_single_dict_loaded(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)
        mem_dir = root / "memory"
        mem_dir.mkdir()
        (mem_dir / "single.json").write_text(
            json.dumps({"content": "Single dict entry"}),
            encoding="utf-8",
        )

        result = load_qwenpaw(root, [])
        memory = result.get("openclaw_memory")
        assert isinstance(memory, list)
        assert len(memory) == 1
        assert memory[0]["content"] == "Single dict entry"

    def test_empty_env_file_no_keys(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)
        secret = root / ".secret"
        secret.mkdir()
        (secret / ".env").write_text("", encoding="utf-8")

        result = load_qwenpaw(root, [])
        assert result.get("env_keys") is None or result.get("env_keys") == []

    def test_plugins_dir_without_skill_md_empty(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws1"
        ws.mkdir()
        _make_agent_json(ws)
        (root / "plugins" / "empty-plugin").mkdir(parents=True)

        result = load_qwenpaw(root, [])
        assert "skills" not in result

    def test_nonexistent_root_empty_result(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw_nonexistent"
        result = load_qwenpaw(root, [])
        assert result == {}

    def test_name_defaults_to_workspace_dirname(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "my-project"
        ws.mkdir()
        data = {"id": "some-id"}
        (ws / "agent.json").write_text(json.dumps(data), encoding="utf-8")

        result = load_qwenpaw(root, [])
        agents = result["qwenpaw_agents"]
        assert agents[0]["name"] == "my-project"

    def test_id_defaults_to_workspace_dirname(self, tmp_path: Path) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "default-workspace"
        ws.mkdir()
        data = {"name": "My Agent"}
        (ws / "agent.json").write_text(json.dumps(data), encoding="utf-8")

        result = load_qwenpaw(root, [])
        agents = result["qwenpaw_agents"]
        assert agents[0]["id"] == "default-workspace"


class TestLoadCompetitorPayloadAPI:
    """Public API edge cases for load_competitor_payload."""

    def test_non_local_mode_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.migration.competitor_payload_loader.is_local_mode",
            lambda: False,
        )
        with pytest.raises(ValueError, match="local or Tauri"):
            load_competitor_payload({"competitor": "qwenpaw", "root": "/tmp", "files": []})

    def test_unsupported_competitor_returns_error(self, _local: None) -> None:
        result = load_competitor_payload({"competitor": "unknown_tool", "root": "/tmp", "files": []})
        assert result.get("_load_error")
        assert "Unsupported" in str(result["_load_error"])

    def test_build_coverage_items_with_load_error(self, _local: None) -> None:
        result = load_competitor_payload({"competitor": "fake", "root": "/tmp", "files": []})
        items = build_coverage_items(result)
        error_row = next((r for r in items if r["key"] == "load_error"), None)
        assert error_row is not None
        assert error_row["status"] == "missing"

    def test_build_coverage_items_empty_payload(self) -> None:
        items = build_coverage_items({})
        mcp_row = next((r for r in items if r["key"] == "mcp"), None)
        assert mcp_row is not None
        assert mcp_row["status"] == "manual"


class TestQwenpawEndToEndDiscovery:
    """Integration test through the public load_competitor_payload API."""

    def test_full_load_via_discovery(self, tmp_path: Path, _local: None) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "project-main"
        ws.mkdir()
        (ws / "system.md").write_text("Be concise.", encoding="utf-8")
        _make_agent_json(
            ws,
            name="Main",
            prompt_files=["system.md"],
            mcp_clients={"github": {"command": "gh-mcp"}},
        )
        mem_dir = root / "memory"
        mem_dir.mkdir()
        (mem_dir / "facts.json").write_text(
            json.dumps([{"content": "User likes Python"}]),
            encoding="utf-8",
        )

        loaded = load_competitor_payload(
            {"competitor": "qwenpaw", "root": str(root), "files": []},
        )
        assert loaded.get("soul_md") == "Be concise."
        assert loaded.get("mcp_servers") == {"github": {"command": "gh-mcp"}}
        assert isinstance(loaded.get("openclaw_memory"), list)

    def test_coverage_items_mcp_ready_with_qwenpaw(self, tmp_path: Path, _local: None) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws"
        ws.mkdir()
        _make_agent_json(ws, mcp_clients={"fs": {"command": "fs-mcp"}})

        loaded = load_competitor_payload(
            {"competitor": "qwenpaw", "root": str(root), "files": []},
        )
        items = build_coverage_items(loaded)
        mcp_row = next((r for r in items if r["key"] == "mcp"), None)
        assert mcp_row is not None
        assert mcp_row["status"] == "ready"

    def test_coverage_items_mcp_manual_without_mcp(self, tmp_path: Path, _local: None) -> None:
        root = tmp_path / ".qwenpaw"
        root.mkdir()
        ws = root / "ws"
        ws.mkdir()
        _make_agent_json(ws)

        loaded = load_competitor_payload(
            {"competitor": "qwenpaw", "root": str(root), "files": []},
        )
        items = build_coverage_items(loaded)
        mcp_row = next((r for r in items if r["key"] == "mcp"), None)
        assert mcp_row is not None
        assert mcp_row["status"] == "manual"
