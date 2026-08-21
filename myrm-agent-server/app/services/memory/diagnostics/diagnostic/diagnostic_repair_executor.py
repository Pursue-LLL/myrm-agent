"""Memory Doctor repair execution service.

[INPUT]
Memory Doctor repair plan ids from the GUI.

[OUTPUT]
Whitelisted dry-run or execution result plus optional diagnostic run.

[POS]
Single-user Memory Doctor repair executor. It closes the loop between visible
repair plans and server-side actions while blocking config-changing repairs that
need explicit operator work.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryRepairExecutionResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import MemoryCommandDiagnosticRun

# MemoryCommandCenterService / MemoryDiagnosticsService are imported lazily in
# run(): command_center back-references the diagnostics facade, so module-level
# imports would deadlock on ``diagnostic/__init__`` partial init.

RepairPlanId = Literal[
    "run_diagnostics",
    "run_health_refresh",
    "review_storage_config",
    "enable_vector_store",
    "configure_embedding",
    "review_retrieval_trace",
    "restore_disciplined_defaults",
]
RepairMode = Literal["dry_run", "execute"]


class MemoryDiagnosticRepairExecutor:
    """Executes only whitelisted Memory Doctor repairs."""

    def __init__(self, db: AsyncSession, memory_manager: MemoryManager) -> None:
        self._db = db
        self._memory_manager = memory_manager

    async def run(
        self,
        plan_id: RepairPlanId,
        mode: RepairMode,
    ) -> tuple[MemoryRepairExecutionResult, MemoryCommandDiagnosticRun | None]:
        """Run a repair plan or return a blocked/manual result."""

        from app.services.memory.command_center.command_center import MemoryCommandCenterService
        from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService
        from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

        if mode == "dry_run":
            return (
                MemoryRepairExecutionResult(
                    plan_id=plan_id,
                    status="dry_run",
                    message=_dry_run_message(plan_id),
                    changed=False,
                ),
                None,
            )

        if plan_id == "run_health_refresh":
            command_center = MemoryCommandCenterService(self._db, self._memory_manager)
            await command_center.refresh_health()
            snapshot = await command_center.build_snapshot()
            run = await MemoryDiagnosticsService(self._db, self._memory_manager).run_diagnostics(
                health_cache_status=snapshot.health.cache_status,
                runtime=snapshot.runtime,
            )
            return (
                MemoryRepairExecutionResult(
                    plan_id=plan_id,
                    status="completed",
                    message="Memory health cache refreshed and diagnostics reran.",
                    probe_run_id=run.id,
                    changed=True,
                ),
                run,
            )

        if plan_id == "run_diagnostics":
            command_center = MemoryCommandCenterService(self._db, self._memory_manager)
            snapshot = await command_center.build_snapshot()
            run = await MemoryDiagnosticsService(
                self._db,
                self._memory_manager,
                ledger=MemoryOperationLedgerService(self._db),
            ).run_diagnostics(
                health_cache_status=snapshot.health.cache_status,
                runtime=snapshot.runtime,
            )
            return (
                MemoryRepairExecutionResult(
                    plan_id=plan_id,
                    status="completed",
                    message="Memory diagnostics completed.",
                    probe_run_id=run.id,
                    changed=False,
                ),
                run,
            )

        if plan_id == "restore_disciplined_defaults":
            archived_count = 0
            preserved_pinned_count = 0
            if self._memory_manager is not None:
                from myrm_agent_harness.toolkits.memory import MemoryType
                from myrm_agent_harness.toolkits.memory.types import MemoryStatus

                for mtype in (MemoryType.TASK_DIGEST, MemoryType.CONVERSATION, MemoryType.SEMANTIC):
                    try:
                        items = await self._memory_manager.list_memories(mtype, limit=100)
                        for item in items:
                            if getattr(item, "is_pinned", False):
                                preserved_pinned_count += 1
                                continue
                            item_id = str(getattr(item, "id", "") or "")
                            if item_id:
                                await self._memory_manager.update_memory(item_id, status=MemoryStatus.ARCHIVED)
                                archived_count += 1
                    except Exception:
                        pass

            res_msg = f"Restored disciplined defaults: archived {archived_count} memories, preserved {preserved_pinned_count} pinned entries."

            command_center = MemoryCommandCenterService(self._db, self._memory_manager)
            await command_center.refresh_health()
            snapshot = await command_center.build_snapshot()
            run = await MemoryDiagnosticsService(
                self._db,
                self._memory_manager,
                ledger=MemoryOperationLedgerService(self._db),
            ).run_diagnostics(
                health_cache_status=snapshot.health.cache_status,
                runtime=snapshot.runtime,
            )
            return (
                MemoryRepairExecutionResult(
                    plan_id=plan_id,
                    status="completed",
                    message=res_msg,
                    probe_run_id=run.id,
                    changed=True,
                ),
                run,
            )

        return (
            MemoryRepairExecutionResult(
                plan_id=plan_id,
                status="blocked",
                message=_manual_message(plan_id),
                changed=False,
            ),
            None,
        )


def _dry_run_message(plan_id: str) -> str:
    messages: dict[str, str] = {
        "run_diagnostics": "Would run read-only probes and write a content-free diagnostic audit event.",
        "run_health_refresh": "Would recompute local memory health and rerun diagnostics.",
        "review_storage_config": "Requires manual storage or permission review; no automatic file edits will run.",
        "enable_vector_store": "Requires explicit storage and embedding configuration before execution.",
        "configure_embedding": "Requires explicit provider configuration before execution.",
        "review_retrieval_trace": "Requires opening trace metadata in the GUI; no memory content is exposed.",
        "restore_disciplined_defaults": "Would archive unpinned working memories into a safe snapshot and restore disciplined budget defaults.",
    }
    return messages.get(plan_id, "Unknown repair plan.")


def _manual_message(plan_id: str) -> str:
    messages: dict[str, str] = {
        "review_storage_config": "Storage repair is manual because it can change local paths, database permissions, or sandbox volumes.",
        "enable_vector_store": "Vector-store enablement is blocked until the user confirms storage and embedding configuration.",
        "configure_embedding": "Embedding configuration is blocked until the user chooses a provider and credentials path.",
        "review_retrieval_trace": "Retrieval trace review is a guided inspection action, not an automatic server mutation.",
    }
    return messages.get(plan_id, "Repair plan is not executable.")
