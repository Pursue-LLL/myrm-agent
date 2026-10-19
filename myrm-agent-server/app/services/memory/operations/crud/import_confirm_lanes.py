"""Instruction, MCP and model lanes applied by the import confirm handler.

[INPUT]
app.services.migration.instruction_writer (POS: 指令车道写入)
app.services.memory.imports.import_ledger (POS: 导入账本)
app.services.memory.operations.crud.import_side_effects (POS: 导入后副作用)

[OUTPUT]
InstructionLanes: the applied instruction result plus the counts and rollback
metadata that the confirm response and ledger need.

[POS]
First write lane of the confirm phase. Kept apart from the handler so the order of
writes (instructions -> MCP -> model -> ledger) stays readable and testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.migration.source.source_migration_types import (
    InstructionApplyResult,
    MigrationWizardOptions,
    SourceInstructionPlan,
    WorkspaceRuleWrite,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstructionLanes:
    """What the instruction lane wrote, including the MCP and model side effects."""

    result: InstructionApplyResult | None
    mcp_imported_disabled_count: int


def plan_from_metadata(raw_plan: dict[str, object]) -> SourceInstructionPlan:
    """Rebuild the reviewed instruction plan from its stored form."""

    workspace_rules: list[WorkspaceRuleWrite] = []
    rules_raw = raw_plan.get("workspace_rules")
    if isinstance(rules_raw, list):
        for item in rules_raw:
            if isinstance(item, dict):
                filename = str(item.get("filename", "")).strip()
                content = str(item.get("content", "")).strip()
                if filename and content:
                    workspace_rules.append(WorkspaceRuleWrite(filename=filename, content=content))

    return SourceInstructionPlan(
        competitor=str(raw_plan.get("competitor", "unknown")),
        agent_persona=str(raw_plan.get("agent_persona", "")),
        global_supplement=str(raw_plan.get("global_supplement", "")),
        workspace_rules=workspace_rules,
    )


def options_from_metadata(raw_options: object) -> MigrationWizardOptions:
    """Rebuild the user's binding choice; defaults match the request schema."""

    if not isinstance(raw_options, dict):
        return MigrationWizardOptions()
    return MigrationWizardOptions(
        target_agent_id=str(raw_options["target_agent_id"]) if raw_options.get("target_agent_id") else None,
        clone_from_agent_id=str(raw_options.get("clone_from_agent_id", "builtin-general")),
        include_episodic=bool(raw_options.get("include_episodic")),
        apply_global_instructions=bool(raw_options.get("apply_global_instructions", True)),
    )


def mcp_configs_from_metadata(raw_plan: dict[str, object]) -> list[dict[str, object]]:
    """Only named MCP entries are writable; anything else was already rejected at review."""

    mcp_configs_raw = raw_plan.get("mcp_configs")
    if not isinstance(mcp_configs_raw, list):
        return []
    return [item for item in mcp_configs_raw if isinstance(item, dict) and item.get("name")]


async def apply_instruction_lanes(
    db: AsyncSession,
    *,
    import_batch_id: str,
    raw_plan: dict[str, object],
    raw_options: object,
    metadata: dict[str, object],
    workspace_root: str | None,
) -> InstructionLanes:
    """Write instructions, MCP configs and model migration, then record the rollback facts."""

    from app.services.memory.imports.import_ledger import MemoryImportLedgerService
    from app.services.memory.operations.crud.import_side_effects import (
        _apply_model_migration,
        _write_migrated_mcp_configs,
    )
    from app.services.migration.instruction_writer import (
        apply_instruction_plan,
        instruction_rollback_record_from_apply,
        instruction_rollback_record_to_metadata,
    )

    plan = plan_from_metadata(raw_plan)
    instruction_result = await apply_instruction_plan(
        plan,
        options_from_metadata(raw_options),
        workspace_root=workspace_root,
    )

    mcp_imported_disabled_count = 0
    mcp_configs_to_write = mcp_configs_from_metadata(raw_plan)
    if mcp_configs_to_write:
        try:
            mcp_imported_disabled_count = await _write_migrated_mcp_configs(mcp_configs_to_write)
        except Exception as mcp_exc:
            # A refused MCP write must not undo the instruction lane; readiness reports it instead.
            logger.warning("MCP config migration write failed (non-fatal): %s", mcp_exc)

    model_migration_data = metadata.get("model_migration")
    if isinstance(model_migration_data, dict):
        await _apply_model_migration(
            model_migration_data,
            target_agent_id=instruction_result.target_agent_id,
        )

    rollback_record = instruction_rollback_record_from_apply(
        instruction_result,
        competitor=plan.competitor,
    )
    await MemoryImportLedgerService(db).merge_batch_metadata(
        import_batch_id,
        {"instruction_rollback": instruction_rollback_record_to_metadata(rollback_record)},
    )
    return InstructionLanes(result=instruction_result, mcp_imported_disabled_count=mcp_imported_disabled_count)
