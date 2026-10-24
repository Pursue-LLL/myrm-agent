"""Bound skill catalog display resolution — SSOT for inline vs hidden skills.

[INPUT]
- backends.skills.types::SkillMetadata (POS: skill metadata)
- backends.skills.types::skill_visible_for_tools (POS: tool-capability skill filter)
- agent.skills.runtime.registry::L1_CATALOG_MAX_TOKENS / estimate_skill_entry_tokens (POS: catalog budget)

[OUTPUT]
- CatalogDisplayResolution: display_skills + hidden_skill_count for catalog delivery
- resolve_catalog_display_skills(): shared inline/hidden logic for meta-tools and runtime inject
- should_mount_skill_search_tool(): gate for conditional skill_search_tool mount

[POS]
Runtime catalog display SSOT. Keeps skill_select_tool schema static while preserving
per-agent cognitive-load rules from get_meta_tools.

Visible vs selectable — the two sets are deliberately different:

- ``display_skills`` is what the model can *see*: full ``name + description`` entries
  within ``L1_CATALOG_MAX_TOKENS``, rendered by
  ``skill_catalog_delivery.render_bound_skills_catalog``.
- ``filtered_skills`` is the full bound list. ``skill_select_tool`` validates against it and
  ``skill_search_tool`` indexes it, so an omitted skill stays *selectable* by an explicit
  name or a search hit.

Selection is token-budgeted, not count-budgeted. Skills are considered in ``always``
first order, then name; an entry that would exceed the budget is omitted. Omitted skills
are counted in ``hidden_count``; their names are intentionally not listed, so the model
never has to guess whether a bare name should be selected or searched.
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


def _sorted_skills(skills_to_inline: list[SkillMetadata]) -> list[SkillMetadata]:
    return sorted(skills_to_inline, key=lambda skill: skill.name)


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

    if skill_configs is not None:
        core_candidates = _sorted_skills(
            [skill for skill in model_visible if skill_configs.get(skill.id, {}).get("is_core", False)]
        )
        display_skills = _select_within_token_budget(core_candidates)
    else:
        always_skills = _sorted_skills([skill for skill in model_visible if skill.always])
        non_always = _sorted_skills([skill for skill in model_visible if not skill.always])
        display_skills = _select_within_token_budget(always_skills + non_always)

    display_names = {skill.name for skill in display_skills}
    hidden_skills = [skill for skill in model_visible if skill.name not in display_names]
    return CatalogDisplayResolution(
        filtered_skills=filtered,
        display_skills=display_skills,
        hidden_skills=hidden_skills,
        hidden_skill_count=len(hidden_skills),
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
