"""Skill Registry

1. INPUT/OUTPUT/POS annotations

[INPUT]
- backends.skills.types::SkillMetadata (POS: skill metadata type definition)

[OUTPUT]
- SkillRegistry: Skill registry class (manages registration, lookup, updates)
- skill_registry: Global skill registry singleton
- get_metadata_summary(): XML-format skill summary (embedded in first HumanMessage ``<bound_skills>``, not tool schema; hidden_skill_count drives dynamic listed/select vs search rules)

[POS]
Skill registry. Manages runtime caches and lookups, primarily for MCP-based skills.

"""

from __future__ import annotations

import logging
from functools import lru_cache
from xml.sax.saxutils import escape, quoteattr

from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.utils.text_utils import get_token_count

logger = logging.getLogger(__name__)

L1_CATALOG_MAX_TOKENS = 2_000
"""L1 catalog token ceiling; wrapper/rules reserve lives in catalog_display."""
MAX_SKILL_FILE_BYTES = 128 * 1024  # 128 KB per skill file
_CONTRACT_TEXT_LIMIT = 160


def _truncate_summary_text(text: str, limit: int = _CONTRACT_TEXT_LIMIT) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def _append_contract_summary(lines: list[str], skill: SkillMetadata) -> None:
    contract = skill.contract
    if contract is None:
        return

    attrs = [
        f"steps={quoteattr(str(len(contract.steps)))}",
        f"judgments={quoteattr(str(len(contract.key_judgments)))}",
        f"traps={quoteattr(str(len(contract.potential_traps)))}",
        f"verifications={quoteattr(str(len(contract.verification_steps)))}",
    ]
    if contract.estimated_duration_seconds is not None:
        attrs.append(f"duration_seconds={quoteattr(f'{contract.estimated_duration_seconds:g}')}")

    lines.append(f" <contract {' '.join(attrs)}>")

    if contract.success_criteria:
        lines.append(f" <success>{escape(_truncate_summary_text(contract.success_criteria))}</success>")

    if contract.dependencies:
        dependency_text = ", ".join(contract.dependencies[:5])
        lines.append(f" <dependencies>{escape(_truncate_summary_text(dependency_text))}</dependencies>")

    for verification in contract.verification_steps[:2]:
        verification_hint = verification.description
        if verification.expected_output:
            verification_hint = f"{verification.description} -> {verification.expected_output}"
        lines.append(f" <verify>{escape(_truncate_summary_text(verification_hint))}</verify>")

    for trap in contract.potential_traps[:2]:
        trap_hint = f"{trap.description}; mitigate: {trap.mitigation}"
        lines.append(f" <trap severity={quoteattr(trap.severity)}>{escape(_truncate_summary_text(trap_hint))}</trap>")

    lines.append(" </contract>")


class SkillRegistry:
    """Runtime skill cache and lookup registry.

    Handles dynamic MCP skill registration and runtime skill lookup.
    Storage-backed skills are loaded via SkillBackendProtocol, not registered here.
    """

    def __init__(self):
        self._skills: dict[str, SkillMetadata] = {}
        self._ipc_mcp_skill_cache: dict[str, SkillMetadata] = {}

    def register(self, skill: SkillMetadata) -> None:
        self._skills[skill.name] = skill
        if skill.is_mcp_skill:
            self._ipc_mcp_skill_cache[skill.name] = skill
            source = f"mcp:{skill.mcp.server}" if skill.mcp else "mcp"
        elif skill.is_storage_skill:
            source = "storage"
        else:
            source = "unknown"
        logger.info("Registered skill: %s (source=%s)", skill.name, source)

    def get_skill(self, name: str) -> SkillMetadata | None:
        return self._skills.get(name)

    def get_mcp_skill_for_ipc(self, name: str) -> SkillMetadata | None:
        """Resolve an MCP skill for PTC/IPC execution across subagent routing passes.

        Prefers the active registry view; falls back to the IPC MCP skill cache
        so an in-flight parent PTC call is never broken when a concurrent
        MCP-less subagent invokes ``clear_mcp_skills()``.
        """
        active = self._skills.get(name)
        if active is not None:
            return active
        return self._ipc_mcp_skill_cache.get(name)

    def list_skills(self) -> list[SkillMetadata]:
        return list(self._skills.values())

    def list_mcp_skills(self) -> list[SkillMetadata]:
        return [skill for skill in self._skills.values() if skill.is_mcp_skill]

    def list_storage_skills(self) -> list[SkillMetadata]:
        return [skill for skill in self._skills.values() if skill.is_storage_skill]

    def clear_mcp_skills(self) -> None:
        """Remove MCP-routed skills before a fresh routing pass.

        Storage-backed skills registered here are preserved.
        """
        removed = [name for name, skill in self._skills.items() if skill.is_mcp_skill]
        for name in removed:
            del self._skills[name]
        if removed:
            logger.info("Cleared %d MCP skill(s) from registry: %s", len(removed), removed)

    def clear(self) -> None:
        self._skills.clear()
        self._ipc_mcp_skill_cache.clear()


skill_registry = SkillRegistry()


def _routing_rules(hidden_skill_count: int) -> list[str]:
    """Dynamic catalog-only rules; generic selection rules live in skill_select_tool."""
    if hidden_skill_count <= 0:
        return []
    return [
        " <routing_rules>",
        " If a listed skill matches the request: use skill_select_tool.",
        " If the user names a skill or its name is known from this conversation: use skill_select_tool directly, even if it is not listed.",
        " If you only know the required capability and cannot identify a name: use skill_search_tool, then skill_select_tool.",
        " </routing_rules>",
    ]


def _render_skill_entry(skill: SkillMetadata) -> list[str]:
    """Render one XML skill entry shared by the catalog and its token estimate."""
    attrs = f"name={quoteattr(skill.name)} available={quoteattr(str(skill.available).lower())} trust={quoteattr(skill.trust.name.lower())}"
    if not skill.available and skill.unavailable_reason:
        attrs += f" reason={quoteattr(skill.unavailable_reason)}"
    if skill.always:
        attrs += ' always="true"'
    if skill.usage_stats.is_stale:
        attrs += ' stale="true"'

    lines = [
        f" <skill {attrs}>",
        f" <description>{escape(skill.description)}</description>",
    ]
    _append_contract_summary(lines, skill)
    lines.append(" </skill>")
    return lines


@lru_cache(maxsize=4096)
def _entry_token_cost(rendered_entry: str) -> int:
    return get_token_count(rendered_entry)


def estimate_skill_entry_tokens(skill: SkillMetadata) -> int:
    """Exact token cost of one rendered catalog entry (cached by rendered bytes)."""
    return _entry_token_cost("\n".join(_render_skill_entry(skill)))


def get_metadata_summary(
    skills: list[SkillMetadata],
    *,
    hidden_skill_count: int = 0,
) -> str:
    """Generate the XML skill catalog body for HumanMessage catalog blocks.

    The caller owns selection. ``catalog_display`` fills this list within
    ``L1_CATALOG_MAX_TOKENS``; skills left out are represented only by
    ``hidden_skill_count`` and are recoverable through ``skill_select_tool``
    (known name) or ``skill_search_tool`` (unknown capability).

    Cache impact: stable catalog bytes keep tool schema bytes stable; catalog
    size still counts toward the cached conversation prefix when present.
    """
    if not skills:
        if hidden_skill_count > 0:
            lines = ["<skills>", *_routing_rules(hidden_skill_count), "</skills>"]
            return "\n".join(lines)
        return "<skills>No skills available.</skills>"

    lines = ["<skills>", *_routing_rules(hidden_skill_count)]
    for skill in skills:
        lines.extend(_render_skill_entry(skill))
    lines.append("</skills>")
    return "\n".join(lines)


__all__ = [
    "L1_CATALOG_MAX_TOKENS",
    "MAX_SKILL_FILE_BYTES",
    "SkillRegistry",
    "estimate_skill_entry_tokens",
    "get_metadata_summary",
    "skill_registry",
]
