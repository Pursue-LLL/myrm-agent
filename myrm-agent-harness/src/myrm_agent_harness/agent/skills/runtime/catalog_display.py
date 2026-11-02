"""Bound skill catalog display resolution — SSOT for inline vs hidden skills.

[INPUT]
- backends.skills.types::SkillMetadata (POS: skill metadata)
- backends.skills.types::skill_visible_for_tools (POS: tool-capability skill filter)
- agent.skills.runtime.registry::L1_CATALOG_MAX_TOKENS / estimate_skill_entry_tokens (POS: catalog budget)

[OUTPUT]
- CatalogDisplayResolution: display_skills + hidden skills + overflow_count for catalog delivery
- resolve_catalog_display_skills(): shared inline/hidden logic for meta-tools, runtime inject and the config preview
- should_mount_skill_search_tool(): gate for conditional skill_search_tool mount

[POS]
Runtime catalog display SSOT. Keeps skill_select_tool schema static while preserving
per-agent cognitive-load rules from get_meta_tools.

Visible vs selectable — the two sets are deliberately different:

- ``display_skills`` is what the model sees in full: ``name + description`` entries within
  ``L1_CATALOG_MAX_TOKENS``, rendered by ``skill_catalog_delivery.render_bound_skills_catalog``.
- ``hidden_skills`` is every other model-visible skill. The catalog still names them (one
  ``<hidden_skill_names>`` line), so the model can select a known name directly and only
  searches when it knows a capability but no name.
- ``filtered_skills`` is the full bound list. ``skill_select_tool`` validates against it and
  ``skill_search_tool`` indexes it, so a hidden skill stays *selectable* by name or search hit.

Who earns a full entry:

- With per-agent configuration (a non-empty ``skill_configs``) an explicit ``is_core`` decides;
  a skill without an explicit flag earns one only when it is ``always``.
- Without configuration (``None`` or empty — one state, so a preview and the runtime cannot
  disagree about ``{}``) every model-visible skill is a candidate.

Candidates are considered ``always`` first, then by name; an entry that would exceed the token
budget is left out (and counted in ``overflow_count``).
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.agent.skills.runtime.registry import (
    L1_CATALOG_MAX_TOKENS,
    estimate_skill_entry_tokens,
)
from myrm_agent_harness.backends.skills.types import SkillMetadata, skill_visible_for_tools

# Leave room for the <skills>, <routing_rules> and <bound_skills> wrappers in the real prompt.
_CATALOG_OVERHEAD_RESERVE = 64


@dataclass(frozen=True, slots=True)
class CatalogDisplayResolution:
    """Resolved catalog slice shown in ``<bound_skills>`` HumanMessage blocks."""

    filtered_skills: list[SkillMetadata]
    display_skills: list[SkillMetadata]
    hidden_skills: list[SkillMetadata]
    hidden_skill_count: int
    overflow_count: int
    """Candidates for a full entry that the token budget left out (a subset of ``hidden_skills``)."""


def _is_inline_candidate(skill: SkillMetadata, skill_configs: dict[str, dict[str, object]]) -> bool:
    """An explicit per-agent ``is_core`` wins; without one only an ``always`` skill earns a full entry."""
    entry = skill_configs.get(skill.id)
    explicit = entry.get("is_core") if entry is not None else None
    return skill.always if explicit is None else bool(explicit)


def _select_within_token_budget(skills: list[SkillMetadata]) -> list[SkillMetadata]:
    """Greedily keep full entries while the rendered catalog stays within budget."""
    remaining = L1_CATALOG_MAX_TOKENS - _CATALOG_OVERHEAD_RESERVE
    selected: list[SkillMetadata] = []
    for skill in skills:
        if remaining <= 0:
            break
        cost = estimate_skill_entry_tokens(skill)
        if cost <= remaining:
            selected.append(skill)
            remaining -= cost
    return selected


def _filter_skills_for_agent_tools(
    skills: list[SkillMetadata],
    *,
    available_tool_names: frozenset[str] | None,
    available_tool_groups: frozenset[str] | None,
) -> list[SkillMetadata]:
    if not skills or (available_tool_names is None and available_tool_groups is None):
        return list(skills)

    tool_names = available_tool_names or frozenset()
    tool_groups = available_tool_groups or frozenset()
    return [skill for skill in skills if skill_visible_for_tools(skill, tool_names, tool_groups)]


def resolve_catalog_display_skills(
    skills: list[SkillMetadata],
    *,
    skill_configs: dict[str, dict[str, object]] | None = None,
    available_tool_names: frozenset[str] | None = None,
    available_tool_groups: frozenset[str] | None = None,
) -> CatalogDisplayResolution:
    """Resolve which bound skills appear in the HumanMessage catalog block."""
    filtered = _filter_skills_for_agent_tools(
        skills,
        available_tool_names=available_tool_names,
        available_tool_groups=available_tool_groups,
    )
    available_skills = [skill for skill in filtered if skill.available]
    model_visible = [skill for skill in available_skills if skill.model_invocable]

    candidates = (
        [skill for skill in model_visible if _is_inline_candidate(skill, skill_configs)]
        if skill_configs
        else model_visible
    )
    display_skills = _select_within_token_budget(sorted(candidates, key=lambda skill: (not skill.always, skill.name)))

    display_names = {skill.name for skill in display_skills}
    hidden_skills = [skill for skill in model_visible if skill.name not in display_names]
    return CatalogDisplayResolution(
        filtered_skills=filtered,
        display_skills=display_skills,
        hidden_skills=hidden_skills,
        hidden_skill_count=len(hidden_skills),
        overflow_count=len(candidates) - len(display_skills),
    )


def should_mount_skill_search_tool(
    skills: list[SkillMetadata],
    *,
    skill_configs: dict[str, dict[str, object]] | None = None,
    available_tool_names: frozenset[str] | None = None,
    available_tool_groups: frozenset[str] | None = None,
) -> bool:
    """Return True when token-budgeted catalog leaves hidden bound skills."""
    if not skills:
        return False
    resolution = resolve_catalog_display_skills(
        skills,
        skill_configs=skill_configs,
        available_tool_names=available_tool_names,
        available_tool_groups=available_tool_groups,
    )
    discoverable = [s for s in resolution.filtered_skills if s.model_invocable and s.available]
    return resolution.hidden_skill_count > 0 and bool(discoverable)


__all__ = [
    "L1_CATALOG_MAX_TOKENS",
    "CatalogDisplayResolution",
    "resolve_catalog_display_skills",
    "should_mount_skill_search_tool",
]
