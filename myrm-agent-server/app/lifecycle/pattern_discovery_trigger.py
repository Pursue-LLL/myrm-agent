"""Pattern discovery trigger — on-demand and scheduled execution helpers.

[INPUT]
- myrm_agent_harness.toolkits.memory.strategies.pattern_discovery (POS: Cross-cycle pattern discovery)
- app.lifecycle.memory_guardian_ops::create_guardian_memory_manager (POS: guardian 上下文 MemoryManager 工厂)
- app.services.agent.platform_config::build_platform_litellm_kwargs (POS: WebUI 默认对话模型）
- app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本)

[OUTPUT]
- run_pattern_discovery_cycle: Called by guardian scheduler on 168h interval
- run_pattern_discovery_once: Manual trigger entry point for API
- record_pattern_discovery_event: Persist results to operation_ledger

[POS]
行为模式发现触发器。管理 Pattern Discovery 的定时执行和手动触发，
将结果写入 operation_ledger 以供 Command Center 时间线和 Evolution Digest 展示。
用 WebUI 默认对话模型构造分析 LLM（guardian 上下文 MemoryManager 本身无 LLM，
pattern discovery 的 LLM 依赖独立于维护预算策略）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms import ChatLiteLLM
    from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import PatternReport

logger = logging.getLogger(__name__)


async def _build_platform_llm() -> ChatLiteLLM | None:
    """Construct a chat model from the WebUI default model for analysis.

    Returns ``None`` when the default model is not configured or unreachable
    so callers can skip gracefully instead of raising. Never falls back to
    process environment variables (platform config is the only source).
    """
    from myrm_agent_harness.toolkits.llms import ChatLiteLLM  # type: ignore[attr-defined]

    from app.services.agent.platform_config import build_platform_litellm_kwargs

    try:
        kwargs = await build_platform_litellm_kwargs()
        model = cast(str | None, kwargs.get("model"))
        api_key = cast(str | None, kwargs.get("api_key"))
        if not model or not api_key:
            logger.info("Pattern discovery: skipped (WebUI default model not configured)")
            return None
        return ChatLiteLLM(
            model=model,
            api_key=api_key,
            api_base=cast(str | None, kwargs.get("api_base")),
            temperature=0,
            max_tokens=4096,
            request_timeout=120.0,
        )
    except Exception as exc:
        logger.warning("Pattern discovery: failed to build platform LLM (non-fatal): %s", exc)
        return None


async def run_pattern_discovery_cycle() -> None:
    """Execute a pattern discovery pass using the WebUI default model.

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

        from app.lifecycle.memory_guardian_ops import create_guardian_memory_manager

        llm = await _build_platform_llm()
        if llm is None:
            return

        manager = await create_guardian_memory_manager()
        report = await run_pattern_discovery(manager, llm)
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
    from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

    pattern_count = len(report.patterns)
    summary = f"Pattern discovery: identified {pattern_count} new behavioral pattern(s)."

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

        from app.lifecycle.memory_guardian_ops import create_guardian_memory_manager

        llm = await _build_platform_llm()
        if llm is None:
            return {"triggered": True, "skipped": True, "reason": "no platform default model configured"}

        manager = await create_guardian_memory_manager()
        report = await run_pattern_discovery(manager, llm)
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
