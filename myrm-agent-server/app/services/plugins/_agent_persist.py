"""Expert persistence for Agent Plugin imports (business layer).

Writes the experts of a package through ``AgentService``:

- experts are validated before anything is written; an invalid one is reported
  and left out, it never aborts the others;
- sub-experts are created first (their ids are needed by the experts that lead
  them); if a write fails, every expert created by this import is deleted again;
- a same-name expert is never silently overwritten: ``install`` creates a renamed
  copy, ``replace`` updates the user's own expert in place (``AgentService``
  snapshots it first, so the previous configuration can be restored) and runs
  last, after every creation succeeded. Built-in experts are never replaced.

[INPUT]
- ._agent_plan::plan_agents, AgentPlan (POS: binding plan, resolution and ordering.)
- ._preview_context::PreviewContext (POS: installed skills/connectors/experts at confirm time.)
- ._models::PluginImportSession, PluginConfirmItem, ComponentFailure (POS: import DTOs.)
- .template_workspace::encode_template_files (POS: bounded workspace template encoding.)
- app.services.agent.agent_service::AgentService (POS: expert CRUD with snapshots.)

[OUTPUT]
- AgentImportEntry: one imported expert with its unresolved references and withheld tools.
- AgentImportOutcome: entries, skipped count and per-expert failures.
- persist_imported_agents: persist the accepted experts of a parsed package.

[POS]
Business-layer write half of expert import; the planning half is ``_agent_plan``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from app.database.dto import AgentCreate, AgentUpdate
from app.services.agent.agent_service import AgentService

from ._agent_plan import AgentPlan, plan_agents
from ._models import ComponentFailure, PluginConfirmItem, PluginImportSession
from ._preview_context import ExistingExpert, PreviewContext, expert_key
from .template_workspace import TEMPLATE_FILES_KEY, encode_template_files

logger = logging.getLogger(__name__)

__all__ = ["AgentImportEntry", "AgentImportOutcome", "persist_imported_agents"]

_MAX_COPY_SUFFIX = 50
_NAME_BUDGET = 230  # leaves room for the copy suffix inside AgentBase.name's 255 limit


@dataclass(frozen=True)
class AgentImportEntry:
    virtual_id: str
    package_name: str
    agent_id: str
    action: str  # "created" | "replaced"
    stored_name: str  # differs from package_name when a same-name copy had to be renamed
    previous_version_saved: bool = False  # replaced experts: a restorable snapshot of the old configuration exists
    withheld_tools: tuple[str, ...] = ()
    unresolved_skills: tuple[str, ...] = ()
    unresolved_connectors: tuple[str, ...] = ()
    unresolved_subagents: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentImportOutcome:
    entries: tuple[AgentImportEntry, ...] = ()
    skipped: int = 0
    failures: tuple[ComponentFailure, ...] = ()

    @property
    def agent_ids(self) -> list[str]:
        return [entry.agent_id for entry in self.entries]


async def persist_imported_agents(
    session: PluginImportSession,
    decisions: list[PluginConfirmItem],
    *,
    context: PreviewContext,
    imported_skill_ids: Mapping[str, str],
    imported_servers: Sequence[str],
) -> AgentImportOutcome:
    """Persist the experts the user accepted (an expert without a decision is not imported)."""
    by_vid = {d.virtual_id: d for d in decisions}
    accepted = [
        (vid, agent)
        for vid, agent in session.agents_by_key.items()
        if (decision := by_vid.get(vid)) is not None and decision.resolution != "skip"
    ]
    skipped = len(session.agents_by_key) - len(accepted)
    if not accepted:
        return AgentImportOutcome(skipped=skipped)

    skills_lower = {name.lower(): skill_id for name, skill_id in imported_skill_ids.items()}
    connectors = set(imported_servers) | set(context.server_names)
    plans = plan_agents(
        accepted,
        resolve_skill=lambda name: skills_lower.get(name.strip().lower()) or context.skill_ids_by_name.get(name.strip().lower()),
        resolve_connector=lambda name: name if name in connectors else None,
        imported_skill_ids=list(imported_skill_ids.values()),
        imported_connectors=list(imported_servers),
    )
    templates = encode_template_files(session.plugin_result.workspace_files).files

    plans, invalid = _drop_invalid(plans, templates)
    replace_targets = {
        plan.virtual_id: target
        for plan in plans
        if (target := _replace_target(by_vid[plan.virtual_id], plan, context)) is not None
    }
    agent_ids = {vid: target.agent_id for vid, target in replace_targets.items()}
    created: list[str] = []
    entries: list[AgentImportEntry] = []
    try:
        for plan in plans:
            if plan.virtual_id in replace_targets:
                continue
            stored_name = await _stored_name(plan, context)
            profile = await AgentService.create_agent(_build_create(plan, stored_name, _sub_ids(plan, agent_ids), templates))
            agent_ids[plan.virtual_id] = profile.id
            created.append(profile.id)
            entries.append(_entry(plan, profile.id, "created", stored_name))
        for plan in plans:
            if (target := replace_targets.get(plan.virtual_id)) is not None:
                restorable = await _replace_expert(target, plan, _sub_ids(plan, agent_ids), templates)
                entries.append(_entry(plan, target.agent_id, "replaced", plan.imported.name, restorable))
    except Exception as exc:
        logger.error("Expert import failed; rolling back %d created expert(s): %s", len(created), exc)
        await _rollback(created)
        applied = tuple(entry for entry in entries if entry.action == "replaced")  # already snapshotted and updated
        applied_ids = {entry.virtual_id for entry in applied}
        failures = [
            ComponentFailure("agent", plan.imported.name, "persist_failed", "Expert could not be saved")
            for plan in plans
            if plan.virtual_id not in applied_ids
        ]
        return AgentImportOutcome(entries=applied, skipped=skipped, failures=(*invalid, *failures))

    return AgentImportOutcome(entries=tuple(entries), skipped=skipped, failures=tuple(invalid))


def _drop_invalid(plans: list[AgentPlan], templates: dict[str, str]) -> tuple[list[AgentPlan], list[ComponentFailure]]:
    """Validate every expert's fields up front; invalid ones are reported and unlinked."""
    invalid: dict[str, ComponentFailure] = {}
    for plan in plans:
        try:
            _build_create(plan, plan.imported.name, [], templates)
        except ValidationError as exc:
            invalid[plan.virtual_id] = ComponentFailure("agent", plan.imported.name, "invalid_agent", _first_error(exc))
    remaining = [plan for plan in plans if plan.virtual_id not in invalid]
    for plan in remaining:
        plan.unresolved_subagents.extend(invalid[key].name for key in plan.sub_keys if key in invalid)
        plan.sub_keys = [key for key in plan.sub_keys if key not in invalid]
    return remaining, list(invalid.values())


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Invalid expert definition"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    return f"Invalid {location}: {first.get('msg', '')}"


def _replace_target(decision: PluginConfirmItem, plan: AgentPlan, context: PreviewContext) -> ExistingExpert | None:
    existing = context.experts_by_name.get(expert_key(plan.imported.name))
    if decision.resolution == "replace" and existing is not None and not existing.is_built_in:
        return existing
    return None


async def _stored_name(plan: AgentPlan, context: PreviewContext) -> str:
    """Package name, or a free ``<name> (imported[ n])`` when a same-name expert exists."""
    name = plan.imported.name
    if expert_key(name) not in context.experts_by_name:
        return name
    base = name[:_NAME_BUDGET]
    for attempt in range(1, _MAX_COPY_SUFFIX + 1):
        candidate = f"{base} (imported)" if attempt == 1 else f"{base} (imported {attempt})"
        if not await AgentService.get_agents_by_name(candidate):
            return candidate
    raise RuntimeError(f"No free copy name for expert {name!r}")


def _sub_ids(plan: AgentPlan, agent_ids: Mapping[str, str]) -> list[str]:
    return [agent_ids[key] for key in plan.sub_keys if key in agent_ids]


def _carried_fields(plan: AgentPlan, sub_ids: list[str]) -> dict[str, object]:
    fields = dict(plan.imported.fields)
    fields["skill_ids"] = list(plan.skill_ids)
    fields["mcp_ids"] = list(plan.mcp_ids)
    if plan.tool_selections:
        fields["mcp_tool_selections"] = plan.tool_selections
    fields["subagent_ids"] = sub_ids
    fields["agent_type"] = "team" if plan.sub_keys else "individual"
    return fields


def _build_create(plan: AgentPlan, stored_name: str, sub_ids: list[str], templates: dict[str, str]) -> AgentCreate:
    fields = _carried_fields(plan, sub_ids)
    if plan.is_entry and templates:
        fields["engine_params"] = {TEMPLATE_FILES_KEY: templates}
    return AgentCreate.model_validate({**fields, "name": stored_name})


async def _replace_expert(target: ExistingExpert, plan: AgentPlan, sub_ids: list[str], templates: dict[str, str]) -> bool:
    """Update the user's own expert in place (its identity stays); True when its previous version was saved."""
    fields = _carried_fields(plan, sub_ids)
    if plan.is_entry and templates:
        existing = await AgentService.get_agent_by_id(target.agent_id)
        current = (existing.metadata or {}).get("engine_params") if existing is not None else None
        fields["engine_params"] = {**(current if isinstance(current, dict) else {}), TEMPLATE_FILES_KEY: templates}
    outcome = await AgentService.update_agent(target.agent_id, AgentUpdate.model_validate(fields))
    if outcome is None:
        raise LookupError(f"Expert {target.agent_id} disappeared during import")
    return outcome.snapshot_saved


async def _rollback(created_ids: list[str]) -> None:
    for agent_id in reversed(created_ids):
        try:
            await AgentService.delete_agent(agent_id)
        except Exception as exc:
            logger.warning("Rollback could not delete imported expert %s: %s", agent_id, exc)


def _entry(plan: AgentPlan, agent_id: str, action: str, stored_name: str, restorable: bool = False) -> AgentImportEntry:
    return AgentImportEntry(
        virtual_id=plan.virtual_id,
        package_name=plan.imported.name,
        agent_id=agent_id,
        action=action,
        stored_name=stored_name,
        previous_version_saved=restorable,
        withheld_tools=plan.imported.withheld_tools,
        unresolved_skills=tuple(plan.unresolved_skills),
        unresolved_connectors=tuple(plan.unresolved_connectors),
        unresolved_subagents=tuple(plan.unresolved_subagents),
    )
