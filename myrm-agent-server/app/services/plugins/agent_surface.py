"""Expert surface of an Agent Plugins package (business layer).

One module owns what of an expert (Agent profile) travels in a plugin package, in
both directions, so export and import can never drift apart:

- ``AGENT_FIELD_DISPOSITION`` classifies every ``AgentBase`` field (default-deny:
  a new field is not shared until someone decides it is; an exhaustiveness test
  fails the build otherwise).
- ``profile_to_plugin_agent`` projects a stored profile onto the portable record.
- ``import_agent_fields`` projects an untrusted package record back onto
  product fields. Imports can only tighten: tool grants are limited to the
  default set and the loop budget can never exceed the system default.

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginAgent (POS: portable agent record.)
- myrm_agent_harness.backends.profiles.types::AgentProfile (POS: stored profile.)
- app.database.dto::PersonalityStyleLiteral (POS: allowed personality presets.)
- app.services.agent.builtin_specs.builtin_tool_ids::DEFAULT_ENABLED_BUILTIN_TOOLS
  (POS: tool grants an untrusted package may enable.)

[OUTPUT]
- Disposition / AGENT_FIELD_DISPOSITION: per-field sharing decision with its reason.
- profile_to_plugin_agent: stored profile -> portable record (export).
- ImportedAgentFields / import_agent_fields: portable record -> product fields (import).
- filter_tool_selections: per-connector tool whitelist limited to resolved connectors.

[POS]
Single source of truth for the expert surface of plugin packages. Pure functions,
no persistence, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, get_args

from myrm_agent_harness.agent.plugins.models import PluginAgent
from myrm_agent_harness.backends.profiles.types import AgentProfile

from app.database.dto import PersonalityStyleLiteral
from app.services.agent.builtin_specs.builtin_tool_ids import DEFAULT_ENABLED_BUILTIN_TOOLS

__all__ = [
    "AGENT_FIELD_DISPOSITION",
    "IMPORTED_MAX_ITERATIONS_CEILING",
    "Disposition",
    "ImportedAgentFields",
    "filter_tool_selections",
    "import_agent_fields",
    "profile_to_plugin_agent",
]


class Disposition(StrEnum):
    """What happens to an ``AgentBase`` field when an expert is packaged."""

    CARRY = "carry"  # written to the package and applied on import (validated, tighten-only)
    REFERENCE = "reference"  # travels as names resolved through the dependency closure, never as local ids
    DISPLAY = "display"  # shown in the import preview, never applied
    DERIVE = "derive"  # recomputed on import
    DROP = "drop"  # never leaves the machine and is never accepted from a package


_C, _R, _D, _V, _X = (
    Disposition.CARRY,
    Disposition.REFERENCE,
    Disposition.DISPLAY,
    Disposition.DERIVE,
    Disposition.DROP,
)

# Every AgentBase field, with the reason for its decision (default-deny).
_FIELD_RULES: Final[dict[str, tuple[Disposition, str]]] = {
    "name": (_C, "identity of the expert"),
    "description": (_C, "identity of the expert"),
    "system_prompt": (_C, "the expert's behavior"),
    "max_iterations": (_C, "loop budget; imports can only lower it to the system default"),
    "enabled_builtin_tools": (_C, "requested tool set; imports are limited to the default grants"),
    "personality_style": (_C, "validated preset"),
    "suggestion_prompts": (_C, "starter prompts (bounded text)"),
    "allow_discovery": (_C, "delegation visibility flag"),
    "mcp_tool_selections": (_C, "per-connector tool whitelist, restricted to resolved connectors"),
    "engine_params": (_C, "only template_workspace_files travels, as workspace templates"),
    "skill_ids": (_R, "resolved as skill names (bundled or preset)"),
    "mcp_ids": (_R, "resolved as connector names (declared without secrets)"),
    "subagent_ids": (_R, "resolved as sub-expert names inside the package"),
    "model_selection": (_D, "provider/model availability is per installation"),
    "agent_type": (_V, "team when sub-experts are linked"),
    "is_built_in": (_V, "imported experts are never built-in"),
    "avatar_url": (_X, "may point at machine-local files"),
    "home_directory": (_X, "machine path"),
    "mounted_skill_ids": (_X, "references other experts' private skills"),
    "skill_configs": (_X, "keyed by installation-local skill ids"),
    "browser_source": (_X, "environment-specific"),
    "dialog_policy": (_X, "environment-specific"),
    "session_recording": (_X, "environment-specific"),
    "security_overrides": (_X, "permission escalation vector; packages never carry security policy"),
    "default_security_preset": (_X, "security policy is the installing user's decision"),
    "required_capabilities": (_X, "channel capabilities are environment-specific"),
    "prompt_mode": (_X, "controls which safety/system sections are injected"),
    "memory_decay_profile": (_X, "personal memory tuning"),
    "memory_extraction_preset": (_X, "personal memory tuning"),
    "workspace_policy": (_X, "isolation policy is the installing user's decision"),
    "memory_policy": (_X, "personal memory tuning"),
    "session_policy": (_X, "channel session policy is environment-specific"),
    "auto_restore_domains": (_X, "persisted login state hosts"),
    "is_pareto_preset": (_X, "product-internal flag"),
    "cost_reduction_ratio": (_X, "product-internal flag"),
    "openapi_services": (_X, "may carry service credentials; reported as not carried"),
    "command_bindings": (_X, "channel slash-command bindings are environment-specific"),
    "notify_targets": (_X, "personal recipients"),
    "tool_gateway_config": (_X, "carries gateway credentials"),
    "cron_post_run_verify": (_X, "unattended-run policy is the installing user's decision"),
    "busy_input_mode": (_X, "personal preference"),
    "a2a_enabled": (_X, "remote orchestration trust"),
    "a2a_trusted_peer_ids": (_X, "remote orchestration trust"),
    "trusted_desktop_apps": (_X, "pre-trusted desktop apps are the installing user's decision"),
    "responsibility_scope": (_X, "owner-specific governance data"),
    "owner_label": (_X, "owner-specific governance data"),
    "acceptance_criteria": (_X, "owner-specific governance data"),
}

AGENT_FIELD_DISPOSITION: Final[Mapping[str, Disposition]] = {name: rule[0] for name, rule in _FIELD_RULES.items()}
"""Sharing decision of every ``AgentBase`` field."""

# An untrusted package may lower the loop budget but never raise it above the system default.
IMPORTED_MAX_ITERATIONS_CEILING: Final = 50
_MIN_ITERATIONS: Final = 5  # AgentBase lower bound

MAX_SUGGESTION_PROMPTS: Final = 6
MAX_SUGGESTION_PROMPT_CHARS: Final = 200
MAX_NAME_CHARS: Final = 255  # AgentBase.name bound
_MAX_TOOL_NAME_CHARS: Final = 128
_MAX_SELECTED_TOOLS: Final = 200

_PERSONALITY_STYLES: Final = frozenset(get_args(PersonalityStyleLiteral))


def profile_to_plugin_agent(
    profile: AgentProfile,
    *,
    skill_names: tuple[str, ...],
    mcp_names: tuple[str, ...],
    subagent_names: tuple[str, ...],
    is_subagent: bool,
    is_entry_agent: bool,
) -> PluginAgent:
    """Project a stored expert onto the portable record (carried fields only)."""
    meta = profile.metadata or {}
    extras: dict[str, object] = {}

    personality = meta.get("personality_style")
    if isinstance(personality, str) and personality in _PERSONALITY_STYLES:
        extras["personality_style"] = personality
    prompts = _bounded_texts(meta.get("suggestion_prompts"), MAX_SUGGESTION_PROMPTS, MAX_SUGGESTION_PROMPT_CHARS)
    if prompts:
        extras["suggestion_prompts"] = prompts
    if meta.get("allow_discovery") is False:  # True is the default; only the deviation travels
        extras["allow_discovery"] = False
    selections = filter_tool_selections(meta.get("mcp_tool_selections"), set(mcp_names))
    if selections:
        extras["mcp_tool_selections"] = selections

    return PluginAgent(
        name=profile.display_name or profile.id,
        description=profile.description or "",
        system_prompt=profile.system_prompt or "",
        max_iterations=profile.max_iterations,
        skill_names=skill_names,
        tool_names=_tool_ids(profile),
        mcp_names=mcp_names,
        subagent_names=subagent_names,
        is_subagent=is_subagent,
        is_entry_agent=is_entry_agent,
        metadata=extras,
    )


@dataclass(frozen=True)
class ImportedAgentFields:
    """Product fields derived from a package record, plus what was held back."""

    name: str
    fields: dict[str, object]  # AgentCreate/AgentUpdate-ready carried fields (no name, skill/mcp/subagent ids)
    requested_tool_selections: dict[str, list[str]]  # to be filtered once connectors are resolved
    granted_tools: tuple[str, ...]  # requested tools the expert is enabled with
    withheld_tools: tuple[str, ...]  # requested tools that are not auto-enabled
    dropped_fields: tuple[str, ...]  # supplied values that were invalid and discarded


def import_agent_fields(agent: PluginAgent) -> ImportedAgentFields:
    """Derive carried product fields from an untrusted package record (tighten-only)."""
    fields: dict[str, object] = {"description": agent.description, "system_prompt": agent.system_prompt}
    dropped: list[str] = []

    if agent.max_iterations is not None:
        fields["max_iterations"] = max(_MIN_ITERATIONS, min(agent.max_iterations, IMPORTED_MAX_ITERATIONS_CEILING))

    requested = tuple(dict.fromkeys(agent.tool_names))
    granted = [tool for tool in requested if tool in DEFAULT_ENABLED_BUILTIN_TOOLS]
    withheld = tuple(tool for tool in requested if tool not in DEFAULT_ENABLED_BUILTIN_TOOLS)
    if granted:
        fields["enabled_builtin_tools"] = granted

    meta = agent.metadata
    if "personality_style" in meta:
        style = meta["personality_style"]
        if isinstance(style, str) and style in _PERSONALITY_STYLES:
            fields["personality_style"] = style
        else:
            dropped.append("personality_style")
    if "suggestion_prompts" in meta:
        prompts = _bounded_texts(meta["suggestion_prompts"], MAX_SUGGESTION_PROMPTS, MAX_SUGGESTION_PROMPT_CHARS)
        if prompts:
            fields["suggestion_prompts"] = prompts
        else:
            dropped.append("suggestion_prompts")
    if "allow_discovery" in meta:
        if isinstance(meta["allow_discovery"], bool):
            fields["allow_discovery"] = meta["allow_discovery"]
        else:
            dropped.append("allow_discovery")

    return ImportedAgentFields(
        name=_display_name(agent),
        fields=fields,
        requested_tool_selections=filter_tool_selections(meta.get("mcp_tool_selections"), None),
        granted_tools=tuple(granted),
        withheld_tools=withheld,
        dropped_fields=tuple(dropped),
    )


def filter_tool_selections(raw: object, connectors: set[str] | None) -> dict[str, list[str]]:
    """Normalize ``{connector: [tool, ...]}``; limit to ``connectors`` when given."""
    if not isinstance(raw, dict):
        return {}
    selections: dict[str, list[str]] = {}
    for connector, tools in raw.items():
        if not isinstance(connector, str) or (connectors is not None and connector not in connectors):
            continue
        names = _bounded_texts(tools, _MAX_SELECTED_TOOLS, _MAX_TOOL_NAME_CHARS)
        if names:
            selections[connector] = names
    return selections


def _display_name(agent: PluginAgent) -> str:
    name = (agent.name or "").strip() or str(agent.metadata.get("slug") or "").strip() or "Imported expert"
    return name[:MAX_NAME_CHARS]


def _tool_ids(profile: AgentProfile) -> tuple[str, ...]:
    tools = profile.tools_allowed
    if tools is None:
        raw = (profile.metadata or {}).get("enabled_builtin_tools")
        tools = [str(item) for item in raw] if isinstance(raw, list) else None
    return tuple(tools or ())


def _bounded_texts(raw: object, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(raw, list):
        return []
    texts = [item.strip()[:max_chars] for item in raw if isinstance(item, str) and item.strip()]
    return texts[:max_items]
