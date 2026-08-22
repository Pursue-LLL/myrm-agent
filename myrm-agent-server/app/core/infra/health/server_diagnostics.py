"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: 健康状态报告结构)
- myrm_agent_harness.observability.diagnostics.protocols::DiagnosticProtocol (POS: 诊断接口)

[OUTPUT]
- ServerDiagnosticsManager: 聚合各类 Server 业务级探针（例如 DLQ、Token 预算等）的管理器。
- run_server_diagnostics: 供 API 路由直接调用的快捷方法，返回业务层健康度列表。

[POS]
Server 层专属业务诊断管理器。负责解耦 API 控制器与内部业务（如 Channel Gateway, Rate Limiter）的监控逻辑。
"""

import logging
from typing import Sequence

from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

logger = logging.getLogger(__name__)


class DLQDiagnostic(DiagnosticProtocol):
    """Dead Letter Queue and Durable Outbound delivery diagnostic probe.

    Evaluates both in-flight / persisted pending outbound deliveries and DLQ failed message counts.
    """

    async def check_health(self) -> HealthReport:
        try:
            from app.core.channel_bridge import get_channel_gateway

            gateway = get_channel_gateway()
            if gateway and gateway.bus:
                failed_count = await gateway.bus._dlq.get_failed_count() if gateway.bus._dlq else 0
                pending_count = await gateway.bus.durable_outbound.count_pending()

                meta_data: dict[str, object] = {
                    "failed_count": failed_count,
                    "pending_outbound_count": pending_count,
                }
                metrics: dict[str, float] = {
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

            # Not initialized yet or unavailable
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

                process = psutil.Process(os.getpid())
                rss_mb = round(process.memory_info().rss / (1024 * 1024), 1)
            except Exception:
                try:
                    import resource

                    # ru_maxrss is in KB on Linux, bytes on macOS
                    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                    import sys

                    scale = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
                    rss_mb = round(usage / scale, 1)
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

            return HealthReport(
                component_name="ExecutionCache",
                status="pass",
                code="OK_EXECUTION_CACHE_ACTIVE",
                meta_data=meta,
                message=(
                    f"Execution cache active ({rss_mb} MB RSS, {warm_units} warm units)"
                    if rss_mb is not None
                    else f"Execution cache active ({warm_units} warm units)"
                ),
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


class AgentColdStartDiagnostic(DiagnosticProtocol):
    """Agent cold-start warm-path readiness and stage latency diagnostic probe.

    Evaluates the readiness of the primary turn-1 execution warm path without consuming
    any LLM tokens. Diagnoses 4 key dimensions:
    1. Model Provider Configuration (credentials & client viability)
    2. Tool Catalog / MCP Registry (lazy index cache status)
    3. ExecutionCache Warm State (warm BuiltExecutionUnit count & idle status)
    4. Storage / DB Liveness & Query Latency (SQLite microsecond-level ping)
    """

    async def check_health(self) -> HealthReport:
        import asyncio
        import time

        ready_phases: list[str] = []
        phase_details: dict[str, object] = {}
        score: int = 0
        status: str = "pass"
        code: str = "OK_AGENT_WARM_PATH_READY"
        fix_suggestions: list[str] = []

        # 1. Model Provider Readiness
        try:
            from app.core.channel_bridge.config_loader import load_user_configs

            configs = await load_user_configs()
            model_name = getattr(configs.model_cfg, "model", "")
            if model_name:
                ready_phases.append("model_ready")
                phase_details["model_provider"] = model_name
                score += 35
            else:
                phase_details["model_provider"] = "unconfigured"
                fix_suggestions.append("Configure a default LLM Provider in Settings -> Models.")
        except Exception as exc:
            phase_details["model_provider_error"] = str(exc)
            fix_suggestions.append("Verify LLM Provider credentials and network connection.")

        # 2. Tool Catalog Readiness
        try:
            from myrm_agent_harness.api import is_registered_action_tool

            # Verify that tool layer registry is loaded and functioning
            has_bash = is_registered_action_tool("bash")
            ready_phases.append("tools_ready")
            phase_details["tools_ssot_active"] = bool(has_bash)
            score += 25
        except Exception as exc:
            phase_details["tools_error"] = str(exc)
            fix_suggestions.append("Check tool catalog plugin registration status.")

        # 3. Execution Cache Warm State
        try:
            from app.services.agent.execution_cache import get_execution_cache

            cache = get_execution_cache()
            warm_units = getattr(cache, "warm_entry_count", 0)
            phase_details["warm_execution_units"] = warm_units
            if warm_units > 0:
                ready_phases.append("cache_warm")
                score += 20
            else:
                score += 10  # Cold cache is acceptable on startup
        except Exception as exc:
            phase_details["cache_error"] = str(exc)

        # 4. Storage / DB Ping Latency
        storage_latency_ms: float | None = None
        try:
            from sqlalchemy import text

            from app.database.connection import get_session

            start_t = time.perf_counter()
            async with asyncio.timeout(1.0):
                async with get_session() as session:
                    await session.execute(text("SELECT 1"))
            storage_latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            ready_phases.append("storage_healthy")
            phase_details["storage_latency_ms"] = storage_latency_ms
            score += 20
        except Exception as exc:
            phase_details["storage_error"] = str(exc)
            fix_suggestions.append("Check database connection and file lock permissions.")

        # Evaluate overall status
        if "model_ready" not in ready_phases:
            status = "warn"
            code = "WARN_AGENT_MODEL_UNCONFIGURED"
            message = "Agent model provider is not configured."
        elif "storage_healthy" not in ready_phases:
            status = "warn"
            code = "WARN_AGENT_STORAGE_UNHEALTHY"
            message = "Agent storage connectivity is degraded."
        elif "cache_warm" in ready_phases:
            status = "pass"
            code = "OK_AGENT_WARM_PATH_WARM"
            message = f"Agent warm-path fully primed (score: {score}/100, storage: {storage_latency_ms}ms)"
        else:
            status = "pass"
            code = "OK_AGENT_WARM_PATH_COLD_READY"
            message = f"Agent warm-path ready (score: {score}/100, cold cache, storage: {storage_latency_ms}ms)"

        detail_items = [f"Phases: {', '.join(ready_phases)}", f"Score: {score}/100"]
        if storage_latency_ms is not None:
            detail_items.append(f"DB ping: {storage_latency_ms}ms")
        if "warm_execution_units" in phase_details:
            detail_items.append(f"Warm units: {phase_details['warm_execution_units']}")

        meta_data: dict[str, object] = {
            "warm_path_score": score,
            "ready_phases": ready_phases,
            "phase_details": phase_details,
        }

        return HealthReport(
            component_name="AgentColdStart",
            status=status,
            code=code,
            meta_data=meta_data,
            message=message,
            detail="; ".join(detail_items),
            fix_suggestion="; ".join(fix_suggestions) if fix_suggestions else None,
            metrics={
                "warm_path_score": float(score),
                "storage_latency_ms": storage_latency_ms or 0.0,
            },
        )


class ServerDiagnosticsManager:
    """Manages and executes all Server-level business diagnostics."""

    def __init__(self) -> None:
        self._probes: list[DiagnosticProtocol] = [
            DLQDiagnostic(),
            ExecutionCacheDiagnostic(),
            AgentColdStartDiagnostic(),
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
