"""Tests for competitor payload instruction/memory split."""

from __future__ import annotations

from app.services.migration.competitor_payload_split import (
    build_instruction_plan,
    extract_memory_payload,
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
    from app.services.migration.competitor_payload_loader import build_coverage_items

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


def test_cursor_rules_go_to_instruction_not_memory() -> None:
    loaded = {
        "_source": "cursor",
        "cursor_rules": [{"name": "style", "content": "Use TypeScript."}],
    }
    plan = build_instruction_plan(loaded)
    memory = extract_memory_payload(loaded, include_episodic=False)

    assert len(plan.workspace_rules) == 1
    assert memory.get("cursor_rules") is None
