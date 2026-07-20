"""Apply competitor instruction plans to Agent profile and global user instructions.

[INPUT]
SourceInstructionPlan, MigrationWizardOptions.
app.services.agent.profile_snapshot_service::ProfileSnapshotService (POS: Agent 配置快照与回滚)

[OUTPUT]
InstructionApplyResult with target_agent_id and rollback metadata.

[POS]
Instruction lane writer for external source migration. Does not use memory import adapters.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from app.database.dto import AgentCreate, AgentUpdate
from app.database.repositories.uow import UnitOfWork
from app.services.agent.agent_service import AgentService
from app.services.agent.profile_snapshot_service import ProfileSnapshotService
from app.services.config.service import config_service
from app.services.migration.source_migration_types import (
    InstructionApplyResult,
    InstructionRollbackRecord,
    MigrationWizardOptions,
    SourceInstructionPlan,
    WorkspaceRuleWrite,
)

logger = logging.getLogger(__name__)

_MIGRATION_BLOCK_PATTERN = re.compile(
    r"<!--\s*myrm-migration:([a-z0-9_-]+)\s*-->.*?<!--\s*/myrm-migration:\1\s*-->",
    re.DOTALL,
)


def migration_block_marker(competitor: str) -> tuple[str, str]:
    source = competitor.strip().lower() or "unknown"
    start = f"<!-- myrm-migration:{source} -->"
    end = f"<!-- /myrm-migration:{source} -->"
    return start, end


def merge_migration_block(existing: str, competitor: str, content: str) -> str:
    """Replace or append a competitor-tagged block at the end of a text field."""

    body = content.strip()
    if not body:
        return existing.strip()

    start, end = migration_block_marker(competitor)
    block = f"{start}\n{body}\n{end}"
    base = existing.strip()
    if not base:
        return block

    pattern = re.compile(
        rf"<!--\s*myrm-migration:{re.escape(competitor.strip().lower() or 'unknown')}\s*-->.*?<!--\s*/myrm-migration:{re.escape(competitor.strip().lower() or 'unknown')}\s*-->",
        re.DOTALL,
    )
    if pattern.search(base):
        return pattern.sub(block, base).strip()
    return f"{base}\n\n{block}"


async def resolve_target_agent_id(
    options: MigrationWizardOptions,
    *,
    competitor: str,
) -> tuple[str, bool]:
    """Return (agent_id, created). Clones from clone_from when target_agent_id is unset."""

    if options.target_agent_id:
        existing = await AgentService.get_agent_by_id(options.target_agent_id)
        if existing is None:
            msg = f"Target agent not found: {options.target_agent_id}"
            raise ValueError(msg)
        return options.target_agent_id, False

    source = await AgentService.get_agent_by_id(options.clone_from_agent_id)
    if source is None:
        msg = f"Clone source agent not found: {options.clone_from_agent_id}"
        raise ValueError(msg)

    display_name = f"Import from {competitor.title()}"
    created = await AgentService.create_agent(
        AgentCreate(
            name=display_name,
            description=f"Migrated from {competitor} external assistant data.",
            system_prompt=source.system_prompt or "",
            skill_ids=[],
            enabled_builtin_tools=source.tools_allowed,
            model_selection=None,
            mcp_ids=[],
            memory_policy=None,
            prompt_mode=str((source.metadata or {}).get("prompt_mode", "full")),
            personality_style=str((source.metadata or {}).get("personality_style", "professional")),
        ),
    )
    return created.id, True


async def apply_instruction_plan(
    plan: SourceInstructionPlan,
    options: MigrationWizardOptions,
    *,
    workspace_root: str | None,
) -> InstructionApplyResult:
    """Write instruction-lane content to agent system prompt, global settings, and workspace rules."""

    target_id, created = await resolve_target_agent_id(options, competitor=plan.competitor)
    profile_snapshot_id: str | None = None
    previous_global = ""
    global_updated = False

    persona = plan.agent_persona.strip()
    if persona:
        async with UnitOfWork() as uow:
            profile_snapshot_id = await ProfileSnapshotService.save_profile_snapshot(
                target_id,
                reason="competitor-migration",
                uow=uow,
            )
        agent = await AgentService.get_agent_by_id(target_id)
        if agent is None:
            raise ValueError(f"Target agent not found after resolve: {target_id}")
        merged = merge_migration_block(agent.system_prompt or "", plan.competitor, persona)
        await AgentService.update_agent(target_id, AgentUpdate(system_prompt=merged))

    if options.apply_global_instructions and plan.global_supplement.strip():
        previous_global, global_updated = await _replace_global_system_instructions(
            plan.global_supplement.strip(),
            plan.competitor,
        )

    rules_written = 0
    rules_skipped = 0
    written_paths: list[str] = []
    if workspace_root and plan.workspace_rules:
        rules_written, rules_skipped, written_paths = _write_workspace_rules(
            workspace_root,
            plan.workspace_rules,
        )

    return InstructionApplyResult(
        target_agent_id=target_id,
        agent_created=created,
        global_instructions_updated=global_updated,
        workspace_rules_written=rules_written,
        workspace_rules_skipped=rules_skipped,
        profile_snapshot_id=profile_snapshot_id,
        previous_global_instructions=previous_global,
        written_rule_paths=tuple(written_paths),
    )


def instruction_rollback_record_from_apply(result: InstructionApplyResult, *, competitor: str) -> InstructionRollbackRecord:
    return InstructionRollbackRecord(
        target_agent_id=result.target_agent_id,
        profile_snapshot_id=result.profile_snapshot_id,
        previous_global_instructions=result.previous_global_instructions,
        global_instructions_updated=result.global_instructions_updated,
        written_rule_paths=result.written_rule_paths,
        competitor=competitor,
        agent_created=result.agent_created,
    )


def instruction_rollback_record_to_metadata(record: InstructionRollbackRecord) -> dict[str, object]:
    return {
        "target_agent_id": record.target_agent_id,
        "profile_snapshot_id": record.profile_snapshot_id,
        "previous_global_instructions": record.previous_global_instructions,
        "global_instructions_updated": record.global_instructions_updated,
        "written_rule_paths": list(record.written_rule_paths),
        "competitor": record.competitor,
        "agent_created": record.agent_created,
    }


def instruction_rollback_record_from_metadata(raw: dict[str, object]) -> InstructionRollbackRecord | None:
    agent_id = raw.get("target_agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        return None
    snapshot_raw = raw.get("profile_snapshot_id")
    snapshot_id = snapshot_raw if isinstance(snapshot_raw, str) and snapshot_raw else None
    previous = raw.get("previous_global_instructions")
    previous_global = previous if isinstance(previous, str) else ""
    global_updated = bool(raw.get("global_instructions_updated"))
    paths_raw = raw.get("written_rule_paths")
    paths: tuple[str, ...] = ()
    if isinstance(paths_raw, list):
        paths = tuple(str(item) for item in paths_raw if isinstance(item, str))
    competitor_raw = raw.get("competitor")
    competitor = competitor_raw if isinstance(competitor_raw, str) else "unknown"
    agent_created = bool(raw.get("agent_created"))
    return InstructionRollbackRecord(
        target_agent_id=agent_id,
        profile_snapshot_id=snapshot_id,
        previous_global_instructions=previous_global,
        global_instructions_updated=global_updated,
        written_rule_paths=paths,
        competitor=competitor,
        agent_created=agent_created,
    )


async def rollback_instruction_plan(record: InstructionRollbackRecord) -> bool:
    """Restore agent profile and global instructions from a migration rollback record."""

    restored = False
    if record.profile_snapshot_id:
        ok = await AgentService.rollback_profile_to_snapshot(
            record.target_agent_id,
            record.profile_snapshot_id,
        )
        restored = restored or ok
    elif record.competitor:
        agent = await AgentService.get_agent_by_id(record.target_agent_id)
        if agent is not None:
            cleaned = _MIGRATION_BLOCK_PATTERN.sub("", agent.system_prompt or "").strip()
            await AgentService.update_agent(record.target_agent_id, AgentUpdate(system_prompt=cleaned))
            restored = True

    if record.global_instructions_updated:
        await config_service.set(
            "personalSettings",
            await _personal_settings_with_instructions(record.previous_global_instructions),
        )
        restored = True

    for rule_path in record.written_rule_paths:
        path = Path(rule_path)
        if path.is_file():
            path.unlink(missing_ok=True)
            restored = True

    return restored


async def _replace_global_system_instructions(supplement: str, competitor: str) -> tuple[str, bool]:
    config_record = await config_service.get("personalSettings")
    if config_record is None:
        logger.warning("personalSettings config missing; skipping global instruction import")
        return "", False

    value = config_record.value
    if not isinstance(value, dict):
        logger.warning("Invalid personalSettings value; skipping global instruction import")
        return "", False

    current = str(value.get("systemInstructions", "") or "")
    merged = merge_migration_block(current, competitor, supplement)
    updated = dict(value)
    updated["systemInstructions"] = merged
    await config_service.set("personalSettings", updated)
    return current, True


async def _personal_settings_with_instructions(instructions: str) -> dict[str, object]:
    record = await config_service.get("personalSettings")
    if record is None or not isinstance(record.value, dict):
        return {"systemInstructions": instructions}
    updated = dict(record.value)
    updated["systemInstructions"] = instructions
    return updated


def _write_workspace_rules(workspace_root: str, rules: list[WorkspaceRuleWrite]) -> tuple[int, int, list[str]]:
    rules_dir = Path(workspace_root) / ".myrm" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    paths: list[str] = []
    for rule in rules:
        path = rules_dir / rule.filename
        if path.exists():
            skipped += 1
            continue
        path.write_text(rule.content, encoding="utf-8")
        written += 1
        paths.append(str(path))
    return written, skipped, paths
