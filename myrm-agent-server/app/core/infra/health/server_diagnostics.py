"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: 健康状态报告结构)
- myrm_agent_harness.observability.diagnostics.protocols::DiagnosticProtocol (POS: 诊断接口)
- app.core.infra.health.agent_diagnostics::AgentColdStartDiagnostic (POS: Agent 预热探针)
- app.core.infra.health.agent_diagnostics::OllamaModelContextDiagnostic (POS: Ollama 64K 上下文探针)
- app.core.infra.health.agent_diagnostics::AgentStepBudgetDiagnostic (POS: Agent 步数预算探针)
- app.core.infra.health.agent_diagnostics::AgentPromptCacheAlignmentDiagnostic (POS: Agent 前缀缓存对齐探针)

[OUTPUT]
- DLQDiagnostic: 死信队列与 Durable Outbound 发送诊断探针。
- ExecutionCacheDiagnostic: 执行单元缓存与进程内存 RSS 占用探针。
- AgentColdStartDiagnostic: Agent 冷启动预热探针（别名重导出）。
- OllamaModelContextDiagnostic: Ollama 64K 上下文探针（别名重导出）。
- AgentStepBudgetDiagnostic: Agent 步数预算探针（别名重导出）。
- AgentPromptCacheAlignmentDiagnostic: Agent 前缀缓存对齐探针（别名重导出）。
- SkillHoardingHealthDiagnostic: 技能库囤积与错但高频低质技能诊断探针（别名重导出）。
- ServerDiagnosticsManager: 聚合各类 Server 业务级探针的管理器。
- run_server_diagnostics: 供 API 路由直接调用的快捷方法，返回业务层健康度列表。

[POS]
Server 层专属业务诊断管理器。负责解耦 API 控制器与内部业务（如 Channel Gateway, Rate Limiter）的监控逻辑。
"""

from __future__ import annotations

import logging
from typing import Sequence

from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

from app.core.infra.health.agent_diagnostics import (
    AgentColdStartDiagnostic,
    AgentPromptCacheAlignmentDiagnostic,
    AgentStepBudgetDiagnostic,
    AnthropicSubscriptionPolicyDiagnostic,
    OllamaModelContextDiagnostic,
)
from app.core.infra.health.skill_diagnostics import (
    SkillHoardingHealthDiagnostic,
)

__all__ = [
    "AgentColdStartDiagnostic",
    "AgentPromptCacheAlignmentDiagnostic",
    "AgentStepBudgetDiagnostic",
    "AnthropicSubscriptionPolicyDiagnostic",
    "DLQDiagnostic",
    "ExecutionCacheDiagnostic",
    "OllamaModelContextDiagnostic",
    "ServerDiagnosticsManager",
    "SkillHoardingHealthDiagnostic",
    "run_server_diagnostics",
]


logger = logging.getLogger(__name__)


class DLQDiagnostic(DiagnosticProtocol):
    """Dead Letter Queue and Durable Outbound delivery diagnostic probe."""

    async def check_health(self) -> HealthReport:
        try:
            from app.core.channel_bridge import get_channel_gateway

            gateway = get_channel_gateway()
            if gateway and gateway.bus:
                failed_count = await gateway.bus._dlq.get_failed_count() if gateway.bus._dlq else 0
                pending_count = await gateway.bus.durable_outbound.count_pending()
                meta_data = {
                    "failed_count": failed_count,
                    "pending_outbound_count": pending_count,
                }
                metrics = {
                    "dlq_failed_count": float(failed_count),
                    "pending_outbound_count": float(pending_count),
                }

                if failed_count > 100 or pending_count > 200:
                    return HealthReport(
                        component_name="DLQ",
                        status="fail",
                        code="ERR_DLQ_CRITICAL",
                        meta_data=meta_data,
                        metrics=metrics,
                        message="Message delivery queue has critical backlog or failures.",
                        detail=f"DLQ has {failed_count} failed messages, {pending_count} pending outbound (critical threshold).",
                        fix_suggestion="Review failed messages in Settings -> DLQ or check channel connectivity.",
                    )
                if failed_count > 10:
                    return HealthReport(
                        component_name="DLQ",
                        status="warn",
                        code="WARN_DLQ_FAILED",
                        meta_data=meta_data,
                        metrics=metrics,
                        message="Message delivery queue has failed messages.",
                        detail=f"DLQ has {failed_count} failed message(s), {pending_count} pending outbound.",
                        fix_suggestion="Review failed messages in Settings -> DLQ.",
                    )
                if pending_count > 50:
                    return HealthReport(
                        component_name="DLQ",
                        status="warn",
                        code="WARN_OUTBOUND_PENDING_BACKLOG",
                        meta_data=meta_data,
                        metrics=metrics,
                        message="Outbound message delivery backlog is accumulating.",
                        detail=f"Durable outbound has {pending_count} pending message(s) waiting for delivery/recovery.",
                        fix_suggestion="Check external channel network connectivity or rate limits.",
                    )

                detail_parts = [f"DLQ has {failed_count} failed message(s)"]
                if pending_count > 0:
                    detail_parts.append(f"{pending_count} pending outbound redelivery")

                return HealthReport(
                    component_name="DLQ",
                    status="pass",
                    code="OK_DLQ_HEALTHY",
                    meta_data=meta_data,
                    metrics=metrics,
                    message="Message delivery is healthy.",
                    detail=", ".join(detail_parts) + ".",
                )

            return HealthReport(
                component_name="DLQ",
                status="warn",
                code="WARN_DLQ_UNAVAILABLE",
                message="DLQ is not configured or initialized.",
            )
        except Exception as e:
            logger.warning("DLQ health check failed: %s", e)
            return HealthReport(
                component_name="DLQ",
                status="warn",
                code="ERR_DLQ_CHECK_FAILED",
                message="Message delivery check encountered an error.",
                detail="DLQ health check error",
            )


class ExecutionCacheDiagnostic(DiagnosticProtocol):
    """Execution cache and memory footprint diagnostic probe."""

    async def check_health(self) -> HealthReport:
        try:
            import os

            from app.services.agent.execution_cache import get_execution_cache

            rss_mb: float | None = None
            try:
                import psutil

                rss_mb = round(psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024), 1)
            except Exception:
                pass

            cache = get_execution_cache()
            idle_s = getattr(cache, "idle_seconds", 1800.0)
            warm_units = getattr(cache, "warm_entry_count", 0)
            reclaimed = getattr(cache, "reclaimed_count", 0)

            detail_parts = [
                (f"Idle timeout: {idle_s:.0f}s" if idle_s > 0 else "Idle reclaim disabled"),
                f"Warm units: {warm_units}",
                f"Reclaimed: {reclaimed}",
            ]
            if rss_mb is not None:
                detail_parts.insert(0, f"Process RSS: {rss_mb} MB")

            meta: dict[str, object] = {
                "idle_timeout_seconds": idle_s,
                "warm_entry_count": warm_units,
                "reclaimed_count": reclaimed,
            }
            if rss_mb is not None:
                meta["process_rss_mb"] = rss_mb

            msg = (
                f"Execution cache active ({rss_mb} MB RSS, {warm_units} warm units)"
                if rss_mb is not None
                else f"Execution cache active ({warm_units} warm units)"
            )
            return HealthReport(
                component_name="ExecutionCache",
                status="pass",
                code="OK_EXECUTION_CACHE_ACTIVE",
                meta_data=meta,
                message=msg,
                detail=", ".join(detail_parts),
            )
        except Exception as e:
            logger.warning("ExecutionCache health check failed: %s", e)
            return HealthReport(
                component_name="ExecutionCache",
                status="pass",
                code="WARN_EXECUTION_CACHE_DEGRADED",
                message="Execution cache is running in degraded mode.",
                detail=str(e),
            )


class ServerDiagnosticsManager:
    """Manages and executes all Server-level business diagnostics."""

    def __init__(self) -> None:
        self._probes: list[DiagnosticProtocol] = [
            DLQDiagnostic(),
            ExecutionCacheDiagnostic(),
            AgentColdStartDiagnostic(),
            OllamaModelContextDiagnostic(),
            AgentStepBudgetDiagnostic(),
            AgentPromptCacheAlignmentDiagnostic(),
            SkillHoardingHealthDiagnostic(),
            AnthropicSubscriptionPolicyDiagnostic(),
        ]

    async def run_all(self) -> Sequence[HealthReport]:
        reports: list[HealthReport] = []
        for probe in self._probes:
            try:
                report = await probe.check_health()
                reports.append(report)
            except Exception as exc:
                logger.error("Probe %s failed unhandled: %s", probe.__class__.__name__, exc)
                reports.append(
                    HealthReport(
                        component_name=probe.__class__.__name__,
                        status="warn",
                        code="ERR_PROBE_CRASH",
                        message="Probe execution failed unexpectedly.",
                        detail=str(exc),
                    )
                )
        return reports


# Singleton instance for quick access
_server_manager = ServerDiagnosticsManager()


async def run_server_diagnostics() -> Sequence[HealthReport]:
    """Run all Server-level diagnostic probes and return their reports."""
    return await _server_manager.run_all()
