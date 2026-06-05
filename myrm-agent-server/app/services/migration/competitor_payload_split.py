"""Split competitor payloads into instruction vs memory lanes.

[INPUT]
Adapter-ready dict from competitor_payload_loader.

[OUTPUT]
CompetitorInstructionPlan and memory-only payload for import adapters.

[POS]
Prevents project instructions (rules, SOUL, AGENTS.md) from being stored as procedural memory.
"""

from __future__ import annotations

import re

from app.services.migration.competitor_migration_types import (
    CompetitorInstructionPlan,
    WorkspaceRuleWrite,
)

_SECTION_BREAK = "\n\n---\n\n"


def build_instruction_plan(loaded: dict[str, object]) -> CompetitorInstructionPlan:
    """Extract instruction-layer content from a loaded competitor payload."""

    competitor = str(loaded.get("_source", "unknown")).strip().lower() or "unknown"
    plan = CompetitorInstructionPlan(competitor=competitor)

    soul = _text(loaded, "soul_md")
    agents = _text(loaded, "agents_md")
    instructions = _text(loaded, "codex_instructions")

    persona_parts: list[str] = []
    if soul:
        persona_parts.append(soul)
    global_parts: list[str] = []

    if agents:
        persona_parts.append(f"## Project instructions (from {competitor})\n\n{agents}")
    if instructions:
        global_parts.append(f"## Tool instructions (from {competitor})\n\n{instructions}")
    rules = loaded.get("cursor_rules")
    if isinstance(rules, list):
        for index, raw in enumerate(rules):
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name", f"rule-{index}")).strip() or f"rule-{index}"
            content = str(raw.get("content", "")).strip()
            if not content:
                continue
            safe_name = _safe_filename(name)
            plan.workspace_rules.append(
                WorkspaceRuleWrite(
                    filename=f"imported-{competitor}-{safe_name}.md",
                    content=content,
                ),
            )

    semantic = loaded.get("semantic")
    if competitor == "claude" and isinstance(semantic, list) and semantic:
        first = semantic[0]
        if isinstance(first, dict):
            claude_md = str(first.get("content", "")).strip()
            if claude_md:
                persona_parts.append(claude_md)

    settings = loaded.get("cursor_settings")
    if isinstance(settings, dict) and settings:
        global_parts.append(
            f"## Cursor settings (from {competitor})\n\n```json\n{_settings_preview(settings)}\n```",
        )

    codex_settings = loaded.get("codex_settings")
    if isinstance(codex_settings, dict) and codex_settings:
        global_parts.append(
            f"## Codex settings (from {competitor})\n\n```json\n{_settings_preview(codex_settings)}\n```",
        )

    claude_settings = loaded.get("claude_settings")
    if isinstance(claude_settings, dict) and claude_settings:
        global_parts.append(
            f"## Claude settings (from {competitor})\n\n```json\n{_settings_preview(claude_settings)}\n```",
        )

    plan.agent_persona = _SECTION_BREAK.join(persona_parts).strip()
    plan.global_supplement = _SECTION_BREAK.join(global_parts).strip()

    mcp_servers = loaded.get("mcp_servers")
    if isinstance(mcp_servers, dict) and mcp_servers:
        plan.mcp_servers = mcp_servers

    return plan


def extract_memory_payload(
    loaded: dict[str, object],
    *,
    include_episodic: bool,
) -> dict[str, object]:
    """Return a memory-adapter payload with instruction keys removed."""

    memory = dict(loaded)
    for key in (
        "soul_md",
        "agents_md",
        "codex_instructions",
        "cursor_rules",
        "cursor_settings",
        "codex_settings",
        "claude_settings",
        "env_keys",
        "skills",
        "openclaw_skills",
        "mcp_servers",
    ):
        memory.pop(key, None)

    if not include_episodic:
        memory.pop("openclaw_sessions", None)

    if str(loaded.get("_source", "")).strip().lower() == "claude":
        memory.pop("semantic", None)

    if str(loaded.get("_source", "")).strip().lower() == "cursor":
        memory.clear()
        memory["_source"] = loaded.get("_source", "cursor")
        memory["_discovery_root"] = loaded.get("_discovery_root", "")

    if str(loaded.get("_source", "")).strip().lower() == "codex":
        memory.pop("codex_settings", None)

    return memory


def has_api_keys(loaded: dict[str, object]) -> bool:
    env_keys = loaded.get("env_keys")
    return isinstance(env_keys, list) and len(env_keys) > 0


def _text(payload: dict[str, object], key: str) -> str:
    raw = payload.get(key)
    return raw.strip() if isinstance(raw, str) else ""


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "-", name.strip().lower())
    return cleaned.strip("-") or "rule"


def _settings_preview(settings: dict[str, object]) -> str:
    import json

    return json.dumps(settings, indent=2, ensure_ascii=False)[:4000]
