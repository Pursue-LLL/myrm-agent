"""Unit tests for competitor memory import adapters (Hermes, OpenClaw, Cursor, Codex).

Validates payload parsing, bucket mapping, warning generation, edge-case handling,
metadata provenance, and skill detection for all four competitor adapters.
"""

from __future__ import annotations

from app.services.memory.import_codex import dry_run_codex
from app.services.memory.import_cursor import dry_run_cursor
from app.services.memory.import_hermes import dry_run_hermes
from app.services.memory.import_openclaw import dry_run_openclaw

# ---------------------------------------------------------------------------
# Hermes adapter
# ---------------------------------------------------------------------------


class TestHermesAdapter:
    """dry_run_hermes maps SOUL.md / MEMORY.md / USER.md / skills correctly."""

    def test_soul_md_maps_to_profile(self) -> None:
        payload = {"soul_md": "I am a helpful coding assistant focused on Python."}
        result = dry_run_hermes(payload)
        assert result.summary.source == "hermes"
        assert result.summary.status == "ready"
        assert "profile" in result.normalized_data
        assert len(result.normalized_data["profile"]) == 1
        item = result.normalized_data["profile"][0]
        assert "Python" in str(item["content"])
        assert item["metadata"]["external_source"] == "hermes"

    def test_memory_md_bullet_parsing(self) -> None:
        md = "# Preferences\n- User likes Python\n- User uses VS Code\n# Facts\n* Works at Acme Corp"
        payload = {"memory_md": md}
        result = dry_run_hermes(payload)
        assert result.summary.source == "hermes"
        semantic = result.normalized_data.get("semantic", [])
        assert len(semantic) == 3
        contents = [item["content"] for item in semantic]
        assert "User likes Python" in contents
        assert "User uses VS Code" in contents
        assert "Works at Acme Corp" in contents

    def test_memory_md_no_bullets_fallback(self) -> None:
        """Plain text without bullets is imported as a single memory."""
        payload = {"memory_md": "The user is a senior developer."}
        result = dry_run_hermes(payload)
        semantic = result.normalized_data.get("semantic", [])
        assert len(semantic) == 1
        assert "senior developer" in semantic[0]["content"]

    def test_user_md_maps_to_profile(self) -> None:
        payload = {"user_md": "- Name: Alice\n- Role: Engineer"}
        result = dry_run_hermes(payload)
        profile = result.normalized_data.get("profile", [])
        assert len(profile) == 2

    def test_agents_md_is_unsupported(self) -> None:
        payload = {"agents_md": "# Agent Config\nSome config", "memory_md": "- fact"}
        result = dry_run_hermes(payload)
        unsupported = [m for m in result.mappings if m.source_bucket == "AGENTS.md"]
        assert len(unsupported) == 1
        assert unsupported[0].status == "unsupported"

    def test_skills_trigger_warning(self) -> None:
        payload = {
            "memory_md": "- a fact",
            "skills": [{"name": "deploy"}, {"name": "test"}],
        }
        result = dry_run_hermes(payload)
        assert "hermes_skills_detected" in result.warnings
        skill_mapping = [m for m in result.mappings if m.source_bucket == "skills"]
        assert skill_mapping[0].status == "unsupported"

    def test_env_keys_trigger_warning(self) -> None:
        payload = {
            "memory_md": "- fact",
            "env_keys": [{"name": "OPENAI_API_KEY"}],
        }
        result = dry_run_hermes(payload)
        assert "hermes_api_keys_detected" in result.warnings

    def test_empty_payload_returns_missing(self) -> None:
        result = dry_run_hermes({})
        assert result.summary.status == "missing"
        assert result.summary.mapped_items == 0

    def test_empty_strings_ignored(self) -> None:
        payload = {"soul_md": "   ", "memory_md": "", "user_md": "  "}
        result = dry_run_hermes(payload)
        assert result.summary.mapped_items == 0

    def test_section_tags_from_memory_md(self) -> None:
        md = "# Coding\n- Prefers Python\n# Tools\n- Uses Docker"
        result = dry_run_hermes({"memory_md": md})
        semantic = result.normalized_data["semantic"]
        tags_sets = [set(item["tags"]) for item in semantic]
        assert any("coding" in tags for tags in tags_sets)
        assert any("tools" in tags for tags in tags_sets)

    def test_combined_payload_correct_counts(self) -> None:
        payload = {
            "soul_md": "I am helpful",
            "memory_md": "- fact A\n- fact B",
            "user_md": "- pref 1",
        }
        result = dry_run_hermes(payload)
        assert result.summary.mapped_items == 4
        assert result.summary.unmapped_items == 0


# ---------------------------------------------------------------------------
# OpenClaw adapter
# ---------------------------------------------------------------------------


class TestOpenClawAdapter:
    """dry_run_openclaw maps sessions, memory entries, and skills."""

    def test_sessions_map_to_episodic(self) -> None:
        payload = {
            "openclaw_sessions": [
                {"title": "Debug session", "summary": "Fixed bug in auth module", "created_at": "2024-01-01T00:00:00Z"},
            ],
        }
        result = dry_run_openclaw(payload)
        assert result.summary.source == "openclaw"
        episodic = result.normalized_data.get("episodic", [])
        assert len(episodic) == 1
        assert "Debug session" in episodic[0]["content"]

    def test_session_with_messages_fallback(self) -> None:
        payload = {
            "openclaw_sessions": [
                {
                    "name": "Chat",
                    "messages": [
                        {"content": "Hello world"},
                        {"content": "How are you?"},
                    ],
                },
            ],
        }
        result = dry_run_openclaw(payload)
        episodic = result.normalized_data["episodic"]
        assert len(episodic) == 1
        assert "Hello world" in episodic[0]["content"]

    def test_memory_entries_map_to_semantic(self) -> None:
        payload = {
            "openclaw_memory": [
                {"content": "User prefers Python", "type": "preference"},
                {"fact": "Works at Acme", "id": "m1"},
            ],
        }
        result = dry_run_openclaw(payload)
        semantic = result.normalized_data.get("semantic", [])
        assert len(semantic) == 2

    def test_empty_memory_entries_skipped(self) -> None:
        payload = {
            "openclaw_memory": [
                {"content": ""},
                {"other_key": "no content"},
                42,
            ],
        }
        result = dry_run_openclaw(payload)
        semantic = result.normalized_data.get("semantic", [])
        assert len(semantic) == 0

    def test_skills_trigger_warning(self) -> None:
        payload = {
            "openclaw_memory": [{"content": "fact"}],
            "openclaw_skills": [{"name": "deploy"}],
        }
        result = dry_run_openclaw(payload)
        assert "openclaw_skills_detected" in result.warnings

    def test_empty_payload(self) -> None:
        result = dry_run_openclaw({})
        assert result.summary.status == "missing"

    def test_metadata_provenance(self) -> None:
        payload = {
            "openclaw_sessions": [
                {"id": "s-123", "title": "Session", "model": "gpt-4", "provider": "openai"},
            ],
        }
        result = dry_run_openclaw(payload)
        item = result.normalized_data["episodic"][0]
        assert item["metadata"]["external_source"] == "openclaw"


# ---------------------------------------------------------------------------
# Cursor adapter
# ---------------------------------------------------------------------------


class TestCursorAdapter:
    """dry_run_cursor maps rules and settings."""

    def test_rules_map_to_procedural(self) -> None:
        payload = {
            "cursor_rules": [
                {"name": "Python style", "content": "Always use type hints", "globs": "*.py"},
                {"name": "Test convention", "body": "Use pytest for all tests"},
            ],
        }
        result = dry_run_cursor(payload)
        assert result.summary.source == "cursor_rules"
        procedural = result.normalized_data.get("procedural", [])
        assert len(procedural) == 2
        assert any("type hints" in str(item["content"]) for item in procedural)

    def test_settings_preferred_language(self) -> None:
        payload = {
            "cursor_settings": {"preferredLanguage": "typescript"},
        }
        result = dry_run_cursor(payload)
        profile = result.normalized_data.get("profile", [])
        assert len(profile) == 1
        assert "typescript" in profile[0]["content"]

    def test_settings_theme_extracted(self) -> None:
        payload = {
            "cursor_settings": {"workbench.colorTheme": "One Dark Pro"},
        }
        result = dry_run_cursor(payload)
        profile = result.normalized_data.get("profile", [])
        assert len(profile) == 1
        assert "One Dark Pro" in profile[0]["content"]

    def test_empty_rules_and_settings_warns(self) -> None:
        payload = {"cursor_rules": [], "cursor_settings": {}}
        result = dry_run_cursor(payload)
        assert "cursor_empty_payload" in result.warnings

    def test_empty_payload_warns(self) -> None:
        result = dry_run_cursor({})
        assert "cursor_empty_payload" in result.warnings

    def test_rule_without_content_skipped(self) -> None:
        payload = {
            "cursor_rules": [
                {"name": "NoContent"},
                {"name": "HasContent", "content": "real content"},
            ],
        }
        result = dry_run_cursor(payload)
        procedural = result.normalized_data.get("procedural", [])
        assert len(procedural) == 1

    def test_metadata_provenance(self) -> None:
        payload = {
            "cursor_rules": [{"name": "Rule A", "content": "content", "globs": "*.ts", "alwaysApply": True}],
        }
        result = dry_run_cursor(payload)
        item = result.normalized_data["procedural"][0]
        assert item["metadata"]["external_source"] == "cursor"


# ---------------------------------------------------------------------------
# Codex adapter
# ---------------------------------------------------------------------------


class TestCodexAdapter:
    """dry_run_codex maps instructions, memory, and settings."""

    def test_instructions_map_to_procedural(self) -> None:
        payload = {"codex_instructions": "Always write tests first. Use TDD approach."}
        result = dry_run_codex(payload)
        assert result.summary.source == "codex"
        procedural = result.normalized_data.get("procedural", [])
        assert len(procedural) == 1
        assert "TDD" in procedural[0]["content"]

    def test_memory_entries_map_to_semantic(self) -> None:
        payload = {
            "codex_memory": [
                {"content": "User prefers functional programming"},
                {"text": "Uses Rust for systems code"},
            ],
        }
        result = dry_run_codex(payload)
        semantic = result.normalized_data.get("semantic", [])
        assert len(semantic) == 2

    def test_settings_model_extracted(self) -> None:
        payload = {"codex_settings": {"model": "o3-mini"}}
        result = dry_run_codex(payload)
        profile = result.normalized_data.get("profile", [])
        assert len(profile) == 1
        assert "o3-mini" in profile[0]["content"]

    def test_empty_payload_warns(self) -> None:
        result = dry_run_codex({})
        assert "codex_empty_payload" in result.warnings

    def test_empty_instructions_ignored(self) -> None:
        payload = {"codex_instructions": "   "}
        result = dry_run_codex(payload)
        procedural = result.normalized_data.get("procedural", [])
        assert len(procedural) == 0

    def test_invalid_memory_entries_skipped(self) -> None:
        payload = {
            "codex_memory": [
                {"content": "valid"},
                42,
                {"no_content_key": True},
            ],
        }
        result = dry_run_codex(payload)
        semantic = result.normalized_data.get("semantic", [])
        assert len(semantic) == 1

    def test_combined_payload(self) -> None:
        payload = {
            "codex_instructions": "Use type hints",
            "codex_memory": [{"content": "User works with Python"}],
            "codex_settings": {"model": "gpt-4o"},
        }
        result = dry_run_codex(payload)
        assert result.summary.mapped_items == 3
        assert "procedural" in result.normalized_data
        assert "semantic" in result.normalized_data
        assert "profile" in result.normalized_data

    def test_metadata_provenance(self) -> None:
        payload = {"codex_instructions": "Be helpful"}
        result = dry_run_codex(payload)
        item = result.normalized_data["procedural"][0]
        assert item["metadata"]["external_source"] == "codex"
