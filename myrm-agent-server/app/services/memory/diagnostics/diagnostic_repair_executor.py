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
from app.services.memory.command_center import MemoryCommandCenterService
from app.services.memory.diagnostics import MemoryDiagnosticsService
from app.services.memory.operation_ledger import MemoryOperationLedgerService

RepairPlanId = Literal[
    "run_diagnostics",
    "run_health_refresh",
    "review_storage_config",
    "enable_vector_store",
    "configure_embedding",
    "review_retrieval_trace",
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
