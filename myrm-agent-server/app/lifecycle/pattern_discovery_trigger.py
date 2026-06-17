"""Pattern discovery trigger — on-demand and scheduled execution helpers.

[INPUT]
- myrm_agent_harness.toolkits.memory.strategies.pattern_discovery (POS: Cross-cycle pattern discovery)
- app.lifecycle.memory_guardian::_create_memory_manager (POS: MemoryManager factory)
- app.services.memory.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本)

[OUTPUT]
- run_pattern_discovery_cycle: Called by guardian scheduler on 168h interval
- run_pattern_discovery_once: Manual trigger entry point for API
- record_pattern_discovery_event: Persist results to operation_ledger

[POS]
行为模式发现触发器。管理 Pattern Discovery 的定时执行和手动触发，
将结果写入 operation_ledger 以供 Command Center 时间线和 Evolution Digest 展示。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import PatternReport

logger = logging.getLogger(__name__)


async def run_pattern_discovery_cycle() -> None:
    """Execute a pattern discovery pass using the consolidation LLM.

    Runs independently of maintenance — the harness-layer strategy handles
    gate checks (memory count >= 50, consolidation count >= 3) and returns
    a skipped report if not ready.

    On success, records the PatternReport into operation_ledger so the
    Command Center timeline and frontend Evolution Digest can display it.
    """
    try:
        from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
            run_pattern_discovery,
        )

        from app.lifecycle.memory_guardian import _create_memory_manager

        manager = await _create_memory_manager()
        if manager._consolidation_llm is None:
            logger.debug("Pattern discovery: skipped (no consolidation LLM)")
            return

        report = await run_pattern_discovery(manager, manager._consolidation_llm)
        if report.skipped:
            logger.info("Pattern discovery: skipped (%s)", report.skip_reason)
        elif report.has_patterns:
            logger.info(
                "Pattern discovery: found %d patterns (%.0fms)",
                len(report.patterns),
                report.duration_ms,
            )
            await record_pattern_discovery_event(report)
        else:
            logger.info("Pattern discovery: found no patterns (%.0fms)", report.duration_ms)
    except Exception as exc:
        logger.warning("Pattern discovery failed (non-fatal): %s", exc)


async def record_pattern_discovery_event(report: PatternReport) -> None:
    """Record pattern discovery results into operation_ledger for Command Center visibility."""
    from app.database.connection import get_session
    from app.services.memory.operation_ledger import MemoryOperationLedgerService

    pattern_count = len(report.patterns)
    summary = f"Pattern discovery: found {pattern_count} behavioral pattern(s) ({report.duration_ms:.0f}ms)"

    try:
        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.MAINTENANCE,
                status=MemoryOperationStatus.SUCCESS,
                summary=summary,
                source="pattern_discovery",
                metadata={
                    "operation": "pattern_discovery",
                    "pattern_count": pattern_count,
                    "memory_count": report.memory_count,
                    "insight_count": report.insight_count,
                    "duration_ms": int(report.duration_ms),
                    "meta_observation": report.meta_observation,
                    "patterns": [p.model_dump() for p in report.patterns],
                },
                commit=True,
            )
    except Exception as exc:
        logger.warning("Failed to record pattern discovery audit event: %s", exc)


async def run_pattern_discovery_once() -> dict[str, object]:
    """Run a single pattern discovery cycle on demand (manual trigger API).

    Respects the harness-layer maturity gate (>= 50 memories, >= 3
    consolidations) — returns a descriptive message if not ready.
    """
    try:
        from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
            run_pattern_discovery,
        )

        from app.lifecycle.memory_guardian import _create_memory_manager

        manager = await _create_memory_manager()
        if manager._consolidation_llm is None:
            return {"triggered": True, "skipped": True, "reason": "no consolidation LLM configured"}

        report = await run_pattern_discovery(manager, manager._consolidation_llm)
        if report.skipped:
            return {"triggered": True, "skipped": True, "reason": report.skip_reason}

        if report.has_patterns:
            await record_pattern_discovery_event(report)

        return {
            "triggered": True,
            "skipped": False,
            "pattern_count": len(report.patterns),
            "duration_ms": report.duration_ms,
            "meta_observation": report.meta_observation,
        }
    except Exception as exc:
        return {"triggered": True, "error": str(exc)}
