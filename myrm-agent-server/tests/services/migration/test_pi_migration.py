"""Tests for Pi migration probe and loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.migration.source.source_payload_loader import load_source_payload
from app.services.migration.source.source_payload_split import (
    build_instruction_plan,
    extract_memory_payload,
)
from app.services.migration.source.source_probes import discover_pi


@pytest.fixture()
def _local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.migration.source.source_payload_loader.is_local_mode",
        lambda: True,
    )


def _make_pi_session_jsonl(session_id: str, messages: list[dict[str, str]]) -> str:
    header = json.dumps(
        {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": "2025-07-01T12:00:00Z",
            "cwd": "/tmp/test-project",
        }
    )
    lines = [header]
    for idx, msg in enumerate(messages):
        entry = json.dumps(
            {
                "id": f"entry-{idx}",
                "type": "message",
                "timestamp": "2025-07-01T12:00:01Z",
                "parentId": None,
                "message": {"role": msg["role"], "content": msg["content"]},
            }
        )
        lines.append(entry)
    return "\n".join(lines)


class TestDiscoverPi:
    def test_discovers_pi_with_agents_md(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text("You are a helpful assistant.", encoding="utf-8")

        result = discover_pi(tmp_path)
        assert result is not None
        assert result.competitor == "pi"
        assert result.confidence in ("medium", "high")
        assert any(f.kind == "agents" for f in result.files)

    def test_discovers_pi_with_sessions(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text("Assistant persona", encoding="utf-8")
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir()
        session_content = _make_pi_session_jsonl(
            "sess-1",
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        )
        (sessions_dir / "sess-1.jsonl").write_text(session_content, encoding="utf-8")

        result = discover_pi(tmp_path)
        assert result is not None
        assert result.confidence == "high"
        assert result.memory_count_estimate == 1

    def test_discovers_pi_with_skills(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "settings.json").write_text("{}", encoding="utf-8")
        skill_dir = agent_dir / "skills" / "lint"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("Lint skill", encoding="utf-8")

        result = discover_pi(tmp_path)
        assert result is not None
        assert result.skill_count == 1

    def test_discovers_pi_with_auth(self, tmp_path: Path) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text("Agent", encoding="utf-8")
        (agent_dir / "auth.json").write_text(
            json.dumps({"anthropic": {"token": "sk-xxx"}, "openai": {"token": "sk-yyy"}}),
            encoding="utf-8",
        )

        result = discover_pi(tmp_path)
        assert result is not None
        assert result.has_api_keys is True

    def test_returns_none_when_no_pi_dir(self, tmp_path: Path) -> None:
        assert discover_pi(tmp_path) is None

    def test_returns_none_when_empty_pi_dir(self, tmp_path: Path) -> None:
        (tmp_path / ".pi" / "agent").mkdir(parents=True)
        assert discover_pi(tmp_path) is None


class TestLoadPi:
    def test_loads_agents_md(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text("You are a test assistant.", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        assert loaded.get("agents_md") == "You are a test assistant."
        assert loaded.get("_source") == "pi"

    def test_loads_settings(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        settings = {"defaultProvider": "anthropic", "defaultModel": "claude-4-sonnet"}
        (agent_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        assert loaded.get("pi_settings") == settings

    def test_loads_auth_as_env_keys(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        auth = {"anthropic": {"token": "sk-ant-xxx"}, "openai": {"token": "sk-xxx"}}
        (agent_dir / "auth.json").write_text(json.dumps(auth), encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        env_keys = loaded.get("env_keys")
        assert isinstance(env_keys, list)
        key_names = [k["name"] for k in env_keys]
        assert "ANTHROPIC_API_KEY" in key_names
        assert "OPENAI_API_KEY" in key_names

    def test_loads_sessions(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        session_content = _make_pi_session_jsonl(
            "test-session",
            [
                {"role": "user", "content": "Build a web server"},
                {"role": "assistant", "content": "I'll create an Express.js server."},
            ],
        )
        (sessions_dir / "test-session.jsonl").write_text(session_content, encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert isinstance(sessions, list)
        assert len(sessions) == 1
        assert sessions[0]["id"] == "test-session"
        assert sessions[0]["message_count"] == 2

    def test_loads_skills(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        skill = agent_dir / "skills" / "deploy"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("Deploy to production", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        skills = loaded.get("skills")
        assert isinstance(skills, list)
        assert len(skills) == 1
        assert skills[0]["name"] == "deploy"

    def test_skips_unsupported_session_version(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps(
            {"type": "session", "version": 99, "id": "future", "timestamp": "2026-01-01T00:00:00Z", "cwd": "/tmp"}
        )
        entry = json.dumps({"id": "e1", "type": "message", "message": {"role": "user", "content": "hi"}})
        (sessions_dir / "future.jsonl").write_text(f"{header}\n{entry}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert sessions is None or (isinstance(sessions, list) and len(sessions) == 0)


class TestPiSessionEdgeCases:
    """Cover error handling paths in _parse_pi_session_file and _extract_pi_auth_keys."""

    def test_empty_session_file_skipped(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "empty.jsonl").write_text("", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert sessions is None or len(sessions) == 0

    def test_bad_json_header_skipped(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "bad.jsonl").write_text(
            "NOT VALID JSON\n" + json.dumps({"type": "message", "message": {"role": "user", "content": "hi"}}),
            encoding="utf-8",
        )

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert sessions is None or len(sessions) == 0

    def test_non_session_header_skipped(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps({"type": "config", "version": 1})
        entry = json.dumps({"type": "message", "message": {"role": "user", "content": "hi"}})
        (sessions_dir / "wrong.jsonl").write_text(f"{header}\n{entry}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert sessions is None or len(sessions) == 0

    def test_bad_json_entry_lines_skipped(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps({"type": "session", "version": 3, "id": "s1", "timestamp": "2025-01-01", "cwd": "/tmp"})
        good = json.dumps({"type": "message", "message": {"role": "user", "content": "hello"}})
        (sessions_dir / "mixed.jsonl").write_text(f"{header}\nNOT_JSON\n{good}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert isinstance(sessions, list) and len(sessions) == 1
        assert sessions[0]["message_count"] == 1

    def test_non_message_entries_skipped(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps({"type": "session", "version": 3, "id": "s2", "timestamp": "2025-01-01", "cwd": "/tmp"})
        tool_call = json.dumps({"type": "tool_call", "tool": "bash"})
        msg = json.dumps({"type": "message", "message": {"role": "user", "content": "hi"}})
        (sessions_dir / "mixed2.jsonl").write_text(f"{header}\n{tool_call}\n{msg}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert isinstance(sessions, list) and len(sessions) == 1
        assert sessions[0]["message_count"] == 1

    def test_message_without_valid_msg_dict_skipped(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps({"type": "session", "version": 3, "id": "s3", "timestamp": "2025-01-01", "cwd": "/tmp"})
        bad_msg = json.dumps({"type": "message", "message": "not a dict"})
        good_msg = json.dumps({"type": "message", "message": {"role": "user", "content": "ok"}})
        (sessions_dir / "badmsg.jsonl").write_text(f"{header}\n{bad_msg}\n{good_msg}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert isinstance(sessions, list) and len(sessions) == 1
        assert sessions[0]["message_count"] == 1

    def test_list_content_blocks_joined(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps({"type": "session", "version": 3, "id": "s4", "timestamp": "2025-01-01", "cwd": "/tmp"})
        list_msg = json.dumps(
            {
                "type": "message",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                        {"type": "tool_use", "name": "bash"},
                    ],
                },
            }
        )
        (sessions_dir / "list.jsonl").write_text(f"{header}\n{list_msg}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert isinstance(sessions, list) and len(sessions) == 1
        assert sessions[0]["message_count"] == 1

    def test_session_with_only_empty_messages_skipped(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps({"type": "session", "version": 3, "id": "s5", "timestamp": "2025-01-01", "cwd": "/tmp"})
        empty_msg = json.dumps({"type": "message", "message": {"role": "user", "content": "  "}})
        (sessions_dir / "empty_msg.jsonl").write_text(f"{header}\n{empty_msg}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert sessions is None or len(sessions) == 0

    def test_non_dict_auth_returns_no_keys(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "auth.json").write_text('"not a dict"', encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        env_keys = loaded.get("env_keys")
        assert env_keys is None or len(env_keys) == 0

    def test_non_string_content_coerced(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        header = json.dumps({"type": "session", "version": 3, "id": "s6", "timestamp": "2025-01-01", "cwd": "/tmp"})
        num_msg = json.dumps({"type": "message", "message": {"role": "user", "content": 42}})
        (sessions_dir / "num.jsonl").write_text(f"{header}\n{num_msg}", encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        sessions = loaded.get("pi_sessions")
        assert isinstance(sessions, list) and len(sessions) == 1
        assert sessions[0]["message_count"] == 1


class TestPiInstructionPlan:
    def test_agents_md_maps_to_instruction(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text("You are a code reviewer.", encoding="utf-8")
        settings = {"defaultProvider": "anthropic", "defaultModel": "claude-4-sonnet"}
        (agent_dir / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        plan = build_instruction_plan(loaded)
        assert "code reviewer" in plan.agent_persona.lower()
        assert "pi settings" in plan.global_supplement.lower()

    def test_pi_sessions_excluded_from_instruction(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "AGENTS.md").write_text("Assistant", encoding="utf-8")
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir()
        session_content = _make_pi_session_jsonl(
            "s1",
            [
                {"role": "user", "content": "test"},
                {"role": "assistant", "content": "ok"},
            ],
        )
        (sessions_dir / "s1.jsonl").write_text(session_content, encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        memory_payload = extract_memory_payload(loaded, include_episodic=True)
        assert "agents_md" not in memory_payload
        assert "pi_settings" not in memory_payload
        assert isinstance(memory_payload.get("pi_sessions"), list)

    def test_pi_sessions_stripped_when_episodic_disabled(self, tmp_path: Path, _local: None) -> None:
        agent_dir = tmp_path / ".pi" / "agent"
        agent_dir.mkdir(parents=True)
        sessions_dir = agent_dir / "sessions"
        sessions_dir.mkdir()
        session_content = _make_pi_session_jsonl(
            "s1",
            [
                {"role": "user", "content": "test"},
                {"role": "assistant", "content": "ok"},
            ],
        )
        (sessions_dir / "s1.jsonl").write_text(session_content, encoding="utf-8")

        loaded = load_source_payload({"competitor": "pi", "root": str(agent_dir), "files": []})
        memory_payload = extract_memory_payload(loaded, include_episodic=False)
        assert "pi_sessions" not in memory_payload
