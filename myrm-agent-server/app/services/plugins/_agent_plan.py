"""Binding plan for the experts of an Agent Plugin package (business layer, pure).

Decides, before anything is written, what each expert of a package is bound to:

- skills and connectors are resolved per expert from the names it declares
  (a name that resolves to nothing is reported, never silently bound);
- the entry expert falls back to everything the package installed when it
  declares nothing (typical for community packages); other experts only get
  what they declare, so importing never widens a sub-expert's reach;
- sub-experts are linked by name inside the package. An entry expert declaring
  no sub-experts leads every other expert of the package (implicit team).
  Links are ordered so sub-experts are created first; a link that would close a
  cycle is dropped.

[INPUT]
- myrm_agent_harness.agent.plugins.models::PluginAgent (POS: parsed package expert.)
- .agent_surface::import_agent_fields, ImportedAgentFields (POS: tighten-only field projection.)

[OUTPUT]
- AgentPlan: what one expert will be created/updated with, plus unresolved references.
- plan_agents: plans in creation order (sub-experts before the experts that link them).

[POS]
Pure planning half of expert persistence; ``_agent_persist`` performs the writes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from myrm_agent_harness.agent.plugins.models import PluginAgent

from .agent_surface import ImportedAgentFields, filter_tool_selections, import_agent_fields

logger = logging.getLogger(__name__)

__all__ = ["AgentPlan", "plan_agents"]


@dataclass
class AgentPlan:
    virtual_id: str
    agent: PluginAgent
    imported: ImportedAgentFields
    is_entry: bool
    skill_ids: list[str] = field(default_factory=list)
    mcp_ids: list[str] = field(default_factory=list)
    tool_selections: dict[str, list[str]] = field(default_factory=dict)
    sub_keys: list[str] = field(default_factory=list)  # virtual ids of linked sub-experts
    unresolved_skills: list[str] = field(default_factory=list)
    unresolved_connectors: list[str] = field(default_factory=list)
    unresolved_subagents: list[str] = field(default_factory=list)


def plan_agents(
    accepted: Sequence[tuple[str, PluginAgent]],
    *,
    resolve_skill: Callable[[str], str | None],
    resolve_connector: Callable[[str], str | None],
    imported_skill_ids: Sequence[str],
    imported_connectors: Sequence[str],
) -> list[AgentPlan]:
    """Plan every accepted expert; the result is ordered sub-experts first."""
    plans = {
        vid: AgentPlan(virtual_id=vid, agent=agent, imported=import_agent_fields(agent), is_entry=agent.is_entry_agent)
        for vid, agent in accepted
    }
    by_name = _name_index(accepted)

    for plan in plans.values():
        _bind_skills(plan, resolve_skill, imported_skill_ids)
        _bind_connectors(plan, resolve_connector, imported_connectors)

    links = {vid: _link_subagents(plan, plans, by_name) for vid, plan in plans.items()}
    order, acyclic = _creation_order(links)
    for vid, sub_keys in acyclic.items():
        plans[vid].sub_keys = sub_keys
    return [plans[vid] for vid in order]


def _name_index(accepted: Sequence[tuple[str, PluginAgent]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for vid, agent in accepted:
        index.setdefault(agent.name.strip().casefold(), vid)
        slug = agent.metadata.get("slug")
        if isinstance(slug, str) and slug.strip():
            index.setdefault(slug.strip().casefold(), vid)
    return index


def _bind_skills(plan: AgentPlan, resolve: Callable[[str], str | None], imported_ids: Sequence[str]) -> None:
    declared = plan.agent.skill_names
    if not declared:
        plan.skill_ids = list(imported_ids) if plan.is_entry else []
        return
    for name in declared:
        skill_id = resolve(name)
        if skill_id is None:
            plan.unresolved_skills.append(name)
        elif skill_id not in plan.skill_ids:
            plan.skill_ids.append(skill_id)


def _bind_connectors(plan: AgentPlan, resolve: Callable[[str], str | None], imported: Sequence[str]) -> None:
    declared = plan.agent.mcp_names
    if not declared:
        plan.mcp_ids = list(imported) if plan.is_entry else []
    else:
        for name in declared:
            connector = resolve(name)
            if connector is None:
                plan.unresolved_connectors.append(name)
            elif connector not in plan.mcp_ids:
                plan.mcp_ids.append(connector)
    plan.tool_selections = filter_tool_selections(plan.imported.requested_tool_selections, set(plan.mcp_ids))


def _link_subagents(plan: AgentPlan, plans: dict[str, AgentPlan], by_name: dict[str, str]) -> list[str]:
    declared = plan.agent.subagent_names
    if not declared:
        # implicit team: the entry expert leads every other expert of the package
        return [vid for vid, other in plans.items() if not other.is_entry and vid != plan.virtual_id] if plan.is_entry else []
    linked: list[str] = []
    for name in declared:
        vid = by_name.get(name.strip().casefold())
        if vid is None or vid == plan.virtual_id:
            plan.unresolved_subagents.append(name)
        elif vid not in linked:
            linked.append(vid)
    return linked


def _creation_order(links: dict[str, list[str]]) -> tuple[list[str], dict[str, list[str]]]:
    """Post-order over the link graph (children first); links closing a cycle are dropped."""
    order: list[str] = []
    state: dict[str, int] = {}  # 1 = being visited, 2 = done
    acyclic: dict[str, list[str]] = {vid: [] for vid in links}

    def visit(node: str) -> None:
        state[node] = 1
        for child in links[node]:
            if state.get(child) == 1:
                logger.warning("Dropped sub-expert link %s -> %s: it would close a cycle", node, child)
                continue
            acyclic[node].append(child)
            if child not in state:
                visit(child)
        state[node] = 2
        order.append(node)

    for node in links:
        if node not in state:
            visit(node)
    return order, acyclic
