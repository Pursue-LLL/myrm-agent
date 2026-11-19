"""Split external source payloads into instruction vs memory lanes.

[INPUT]
Adapter-ready dict from source_payload_loader.
myrm_agent_harness.api::redact_nested, redact_field_text (POS: shared walker and field-aware credential check of the redaction domain)

[OUTPUT]
SourceInstructionPlan and memory-only payload for import adapters. The settings files (Cursor, Codex, Claude, Pi)
enter the plan's global supplement without their credentials: an ``env`` / ``headers`` block keeps its names only,
and a string holding a credential is replaced whole.

[POS]
Prevents project instructions (rules, SOUL, AGENTS.md) from being stored as procedural memory, and keeps credentials
out of the supplement that the review session stores and the confirm step writes into the global instructions.
"""

from __future__ import annotations

import json
import re

from myrm_agent_harness.api import redact_field_text, redact_nested

from ..env_secrets import KEY_FROM_ENV
from .source_migration_types import (
    SourceInstructionPlan,
    WorkspaceRuleWrite,
)

_SECTION_BREAK = "\n\n---\n\n"

# The settings blocks that hold one secret per member: Claude's ``env``, an MCP server's ``env`` and ``headers``.
_NAMES_ONLY_BLOCKS = frozenset({"env", "headers"})
_REDACTED = "[redacted]"
# The nesting the shared walker keeps; it cuts what lies deeper, so this walk only has to stop before the stack does.
_MAX_DEPTH = 32


def build_instruction_plan(loaded: dict[str, object]) -> SourceInstructionPlan:
    """Extract instruction-layer content from a loaded competitor payload."""

    competitor = str(loaded.get("_source", "unknown")).strip().lower() or "unknown"
    plan = SourceInstructionPlan(competitor=competitor)

    soul = _text(loaded, "soul_md")
    agents = _text(loaded, "agents_md")
    instructions = _text(loaded, "codex_instructions")
    claude_md = _text(loaded, "claude_md")

    persona_parts: list[str] = []
    if soul:
        persona_parts.append(soul)
    global_parts: list[str] = []

    if agents:
        persona_parts.append(f"## Project instructions (from {competitor})\n\n{agents}")
    if claude_md:
        persona_parts.append(claude_md)
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

    pi_settings = loaded.get("pi_settings")
    if isinstance(pi_settings, dict) and pi_settings:
        global_parts.append(
            f"## Pi settings (from {competitor})\n\n```json\n{_settings_preview(pi_settings)}\n```",
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
        "claude_md",
        "codex_instructions",
        "cursor_rules",
        "cursor_settings",
        "codex_settings",
        "claude_settings",
        "pi_settings",
        "env_keys",
        "skills",
        "openclaw_skills",
        "mcp_servers",
        "sessions",
    ):
        memory.pop(key, None)

    if not include_episodic:
        memory.pop("openclaw_sessions", None)
        memory.pop("pi_sessions", None)

    if str(loaded.get("_source", "")).strip().lower() == "codex":
        memory.pop("codex_settings", None)

    return memory


def has_api_keys(loaded: dict[str, object]) -> bool:
    env_keys = loaded.get("env_keys")
    return isinstance(env_keys, list) and len(env_keys) > 0


def has_importable_keys(loaded: dict[str, object]) -> bool:
    """Whether the payload names keys of the source's ``.env``, the one place the opt-in key import reads."""

    env_keys = loaded.get("env_keys")
    return isinstance(env_keys, list) and any(isinstance(item, dict) and item.get("source") == KEY_FROM_ENV for item in env_keys)


def _text(payload: dict[str, object], key: str) -> str:
    raw = payload.get(key)
    return raw.strip() if isinstance(raw, str) else ""


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "-", name.strip().lower())
    return cleaned.strip("-") or "rule"


def _settings_preview(settings: dict[str, object]) -> str:
    """Render a settings file as the JSON the global supplement shows, without its credentials.

    The supplement is stored with the review session and read by the model, so it must not carry a secret or a
    fragment of one: the display mask of the shared redactor keeps the head and tail of a long secret.
    """
    shown = redact_nested(_names_only(settings, depth=1), _credential_free, mask_keys=True)
    return json.dumps(shown, indent=2, ensure_ascii=False)[:4000]


def _names_only(value: object, *, depth: int) -> object:
    """Copy of ``value`` whose ``env`` / ``headers`` blocks list their names without the values.

    Any variable can hold a secret whatever its name says, so the block cannot be judged value by value.
    """
    if depth > _MAX_DEPTH or not isinstance(value, dict | list):
        return value
    if isinstance(value, list):
        return [_names_only(item, depth=depth + 1) for item in value]
    return {
        key: list(item)
        if isinstance(key, str) and key.lower() in _NAMES_ONLY_BLOCKS and isinstance(item, dict)
        else _names_only(item, depth=depth + 1)
        for key, item in value.items()
    }


def _credential_free(key: str, text: str) -> str:
    """``text`` itself, or a marker when the shared redactor would change it (the value of field ``key``)."""
    return text if redact_field_text(key, text) == text else _REDACTED
