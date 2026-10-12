"""Cognitive task executors partitioned by HOPE frequency cadences.

[INPUT]
- app.lifecycle.memory_guardian_ops::(create_guardian_memory_manager, auto_resolve_expired_conflicts,
  purge_expired_archives, harvest_session_blind_spots, sync_external_harness_transcripts, run_sqlite_backup)
- app.services.memory.ledger.guardian_events::(record_maintenance_event, record_purge_audit,
  record_conflict_auto_resolve_event, record_health_snapshot)
- app.lifecycle.pattern_discovery_trigger::run_pattern_discovery_cycle

[OUTPUT]
- execute_t1_session_debounce: Debounced post-turn/session evidence consolidation.
- execute_t2_idle_maintenance: Comprehensive macro-idle maintenance pipeline.
- execute_t3_epoch_discovery: Weekly cross-session pattern discovery.

[POS]
Server lifecycle tier. Encapsulates concrete memory maintenance routines
freeing coordinator and guardians from business sub-task implementation.
"""

from __future__ import annotations

import logging
from typing import Optional

from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.lifecycle.memory_guardian_ops import (
    auto_resolve_expired_conflicts,
    create_guardian_memory_manager,
    harvest_session_blind_spots,
    purge_expired_archives,
    run_sqlite_backup,
    sync_external_harness_transcripts,
)
from app.lifecycle.pattern_discovery_trigger import run_pattern_discovery_cycle
from app.services.memory.ledger.guardian_events import (
    record_conflict_auto_resolve_event,
    record_health_snapshot,
    record_maintenance_event,
    record_purge_audit,
)
from app.services.memory.ledger.guardian_policy import MemoryGuardianPolicy

logger = logging.getLogger(__name__)


async def execute_t1_session_debounce(session_id: str) -> bool:
    """T1 Meso-Session tick: handle asynchronous post-turn consolidation with debouncing."""
    logger.debug("CognitiveClock T1: executing debounced session digestion for %s", session_id)
    try:
        # Non-blocking async blind spot check for recent sessions
        await harvest_session_blind_spots()
        return True
    except Exception as exc:
        logger.warning("CognitiveClock T1: session digest failed for %s: %s", session_id, exc)
        return False


async def execute_t2_idle_maintenance(
    *,
    force: bool = False,
    policy: Optional[MemoryGuardianPolicy] = None,
) -> tuple[Optional[MaintenanceReport], Optional[str]]:
    """T2 Macro-Idle tick: execute full autonomous memory maintenance pipeline."""
    active_policy = policy or MemoryGuardianPolicy()
    try:
        manager = await create_guardian_memory_manager()
        report = await manager.run_maintenance_cycle(force=force)

        if report.skipped:
            logger.info("CognitiveClock T2: maintenance skipped (%s)", report.skip_reason)
            return report, report.skip_reason

        # 1. Purge expired archives
        purged = await purge_expired_archives(manager)
        if purged > 0:
            await record_purge_audit(purged_count=purged, policy=active_policy)

        # 2. Auto-resolve low-risk conflicts
        resolved = await auto_resolve_expired_conflicts()
        if resolved > 0:
            await record_conflict_auto_resolve_event(resolved_count=resolved, policy=active_policy)

        # 3. Harvest blind spots
        await harvest_session_blind_spots()

        # 4. Sync external transcripts
        await sync_external_harness_transcripts()

        # 5. Ledger audit event
        await record_maintenance_event(report=report, forced=force, policy=active_policy)

        # 6. Health snapshot for the Command Center (the executor does not know the next-run countdown)
        await record_health_snapshot(report, policy=active_policy, guardian_running=True)

        # 7. Hot SQLite backup
        await run_sqlite_backup()

        return report, None
    except Exception as exc:
        logger.error("CognitiveClock T2: maintenance execution failed: %s", exc, exc_info=True)
        return None, str(exc)


async def execute_t3_epoch_discovery() -> None:
    """T3 Epoch-Macro tick: trigger weekly cross-session pattern discovery.

    The cycle records its own outcome and never raises, so the tick needs no extra guard.
    """
    logger.info("CognitiveClock T3: starting weekly pattern discovery cycle")
    await run_pattern_discovery_cycle()
