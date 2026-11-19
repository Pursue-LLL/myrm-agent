"""Tests for competitor payload instruction/memory split."""

from __future__ import annotations

import pytest

from app.services.migration.source.source_payload_split import (
    build_instruction_plan,
    extract_memory_payload,
    has_api_keys,
    has_importable_keys,
)


def test_hermes_splits_soul_from_memory() -> None:
    loaded = {
        "_source": "hermes",
        "soul_md": "You are kind.",
        "memory_md": "- Likes tea",
        "user_md": "- Name: Ada",
        "agents_md": "Always cite sources.",
    }
    plan = build_instruction_plan(loaded)
    memory = extract_memory_payload(loaded, include_episodic=False)

    assert "kind" in plan.agent_persona
    assert "cite sources" in plan.agent_persona
    assert "soul_md" not in memory
    assert memory.get("memory_md") == "- Likes tea"


def test_user_md_stays_in_memory_lane() -> None:
    loaded = {
        "_source": "hermes",
        "user_md": "- Name: Ada",
        "soul_md": "Be kind.",
    }
    memory = extract_memory_payload(loaded, include_episodic=False)

    assert memory.get("user_md") == "- Name: Ada"
    assert "soul_md" not in memory


def test_openclaw_soul_maps_to_instruction_lane() -> None:
    loaded = {
        "_source": "openclaw",
        "soul_md": "Be concise.",
        "memory_md": "- likes tea",
    }
    plan = build_instruction_plan(loaded)
    memory = extract_memory_payload(loaded, include_episodic=False)

    assert "concise" in plan.agent_persona
    assert memory.get("memory_md") == "- likes tea"
    assert "soul_md" not in memory


def test_agents_md_goes_to_agent_persona() -> None:
    loaded = {"_source": "hermes", "agents_md": "Always verify facts."}
    plan = build_instruction_plan(loaded)

    assert "verify facts" in plan.agent_persona
    assert not plan.global_supplement.strip()


def test_build_coverage_items_four_lanes() -> None:
    from app.services.migration.source.source_payload_loader import build_coverage_items

    rows = build_coverage_items(
        {
            "soul_md": "x",
            "memory_md": "y",
            "skills": [{"name": "s"}],
            "env_keys": [{"name": "OPENAI_API_KEY"}],
        },
    )
    labels = {row["label"] for row in rows}
    assert "instruction_lane" in labels
    assert "memory_lane" in labels
    assert "skills_review" in labels
    assert "api_keys_manual" in labels
    assert "mcp_manual" in labels
    assert "channels_manual" in labels


def test_pi_payload_builds_correct_coverage_items() -> None:
    from app.services.migration.source.source_payload_loader import build_coverage_items

    rows = build_coverage_items(
        {
            "agents_md": "You are a coder.",
            "pi_sessions": [{"id": "s1", "messages": []}],
            "skills": [{"name": "deploy"}],
            "env_keys": [{"name": "ANTHROPIC_API_KEY"}],
        },
    )
    labels = {row["label"] for row in rows}
    assert "instruction_lane" in labels
    assert "memory_lane" in labels
    assert "skills_review" in labels
    assert "api_keys_manual" in labels


def test_pi_settings_go_to_global_supplement_not_memory() -> None:
    loaded = {
        "_source": "pi",
        "agents_md": "You are a DevOps engineer.",
        "pi_settings": {"defaultProvider": "anthropic", "defaultModel": "claude-4-sonnet"},
        "pi_sessions": [{"id": "s1", "messages": [{"role": "user", "content": "hi"}]}],
    }
    plan = build_instruction_plan(loaded)
    memory = extract_memory_payload(loaded, include_episodic=True)

    assert "DevOps" in plan.agent_persona
    assert "Pi settings" in plan.global_supplement
    assert "pi_settings" not in memory
    assert "agents_md" not in memory
    assert "pi_sessions" in memory


def test_cursor_rules_go_to_instruction_not_memory() -> None:
    loaded = {
        "_source": "cursor",
        "cursor_rules": [{"name": "style", "content": "Use TypeScript."}],
    }
    plan = build_instruction_plan(loaded)
    memory = extract_memory_payload(loaded, include_episodic=False)

    assert len(plan.workspace_rules) == 1
    assert memory.get("cursor_rules") is None


def test_only_the_names_taken_from_the_dotenv_are_keys_the_import_can_read() -> None:
    from_env = {"env_keys": [{"name": "OPENAI_API_KEY", "source": "env"}]}
    from_credential_store = {"env_keys": [{"name": "OPENAI_API_KEY", "source": "auth"}]}

    assert has_importable_keys(from_env) is True
    assert has_importable_keys(from_credential_store) is False
    assert has_importable_keys({"env_keys": []}) is False
    assert has_importable_keys({}) is False


def test_a_name_from_any_store_is_a_key_the_source_holds() -> None:
    assert has_api_keys({"env_keys": [{"name": "OPENAI_API_KEY", "source": "auth"}]}) is True
    assert has_api_keys({"env_keys": []}) is False


# A settings file is shown to the model through the global instructions and stored with the review session, yet it
# also holds credentials: an ``env`` block, an ``apiKey``, a token pasted into a hook command.
CREDENTIAL = "PLACEHOLDER_SETTINGS_CREDENTIAL_k9X2"
HOOK_COMMAND = f"curl -H 'Authorization: Bearer {CREDENTIAL}' https://hooks.example.test/notify"

CLAUDE_SETTINGS: dict[str, object] = {
    "model": "opus",
    "permissions": {"allow": ["Bash(git status:*)"]},
    "env": {
        "ANTHROPIC_AUTH_TOKEN": CREDENTIAL,
        "ANTHROPIC_BASE_URL": "https://gateway.example.test",
        "MY_SERVICE_LOGIN": CREDENTIAL,
    },
    "hooks": {"Stop": [{"command": HOOK_COMMAND}]},
    "mcpServers": {
        "github": {"command": "npx", "args": ["-y", "server-github"], "env": {"GITHUB_PAT": CREDENTIAL}},
        "remote": {"url": "https://mcp.example.test/sse", "headers": {"X-Tenant-Login": CREDENTIAL}},
    },
}
CODEX_SETTINGS: dict[str, object] = {
    "model": "o3",
    "providers": {"openai": {"baseURL": "https://api.example.test/v1", "envKey": "OPENAI_API_KEY", "apiKey": CREDENTIAL}},
}
PI_SETTINGS: dict[str, object] = {"defaultProvider": "anthropic", "defaultModel": "claude-sonnet", "apiKey": CREDENTIAL}
CURSOR_SETTINGS: dict[str, object] = {"editor.fontSize": 14, "cursor.cpp.apiKey": CREDENTIAL}


@pytest.mark.parametrize(
    ("competitor", "settings_key", "settings"),
    [
        ("claude", "claude_settings", CLAUDE_SETTINGS),
        ("codex", "codex_settings", CODEX_SETTINGS),
        ("pi", "pi_settings", PI_SETTINGS),
        ("cursor", "cursor_settings", CURSOR_SETTINGS),
    ],
)
def test_a_settings_block_carries_no_part_of_a_credential(
    competitor: str,
    settings_key: str,
    settings: dict[str, object],
) -> None:
    plan = build_instruction_plan({"_source": competitor, settings_key: settings})

    assert "settings (from" in plan.global_supplement
    # The display mask of a long secret keeps its head and tail, so a fragment is checked too.
    for fragment in (CREDENTIAL, "PLACEHOLDER", "k9X2"):
        assert fragment not in plan.global_supplement


def test_the_settings_that_are_no_credential_stay_readable() -> None:
    claude = build_instruction_plan({"_source": "claude", "claude_settings": CLAUDE_SETTINGS}).global_supplement
    codex = build_instruction_plan({"_source": "codex", "codex_settings": CODEX_SETTINGS}).global_supplement
    pi = build_instruction_plan({"_source": "pi", "pi_settings": PI_SETTINGS}).global_supplement

    assert '"model": "opus"' in claude
    assert "Bash(git status:*)" in claude
    assert "https://mcp.example.test/sse" in claude
    assert '"command": "npx"' in claude
    # ``envKey`` names the variable that holds the key; it is not the key.
    assert '"envKey": "OPENAI_API_KEY"' in codex
    assert "https://api.example.test/v1" in codex
    assert '"defaultModel": "claude-sonnet"' in pi


def test_an_env_or_headers_block_keeps_its_variable_names_and_drops_every_value() -> None:
    supplement = build_instruction_plan({"_source": "claude", "claude_settings": CLAUDE_SETTINGS}).global_supplement

    # ``MY_SERVICE_LOGIN`` and ``X-Tenant-Login`` are no credential by name: only the block can tell.
    for name in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "MY_SERVICE_LOGIN", "GITHUB_PAT", "X-Tenant-Login"):
        assert f'"{name}"' in supplement
    assert "gateway.example.test" not in supplement


def test_a_string_with_a_credential_inside_is_replaced_as_a_whole() -> None:
    supplement = build_instruction_plan({"_source": "claude", "claude_settings": CLAUDE_SETTINGS}).global_supplement

    assert '"command": "[redacted]"' in supplement
    assert "hooks.example.test" not in supplement


def test_a_source_without_settings_adds_no_settings_block() -> None:
    assert build_instruction_plan({"_source": "claude", "claude_md": "Be brief."}).global_supplement == ""
