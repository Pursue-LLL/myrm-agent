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

from myrm_agent_harness.observability.diagnostics.protocols import DiagnosticProtocol, HealthReport

logger = logging.getLogger(__name__)


class DLQDiagnostic(DiagnosticProtocol):
    """Dead Letter Queue diagnostic probe."""

    async def check_health(self) -> HealthReport:
        try:
            from app.core.channel_bridge import get_channel_gateway

            gateway = get_channel_gateway()
            if gateway and gateway.bus and gateway.bus._dlq:
                failed_count = await gateway.bus._dlq.get_failed_count()
                if failed_count > 100:
                    return HealthReport(
                        component_name="DLQ",
                        status="fail",
                        code="ERR_DLQ_CRITICAL",
                        meta_data={"failed_count": failed_count},
                        message="Message delivery queue has critical failures.",
                        detail=f"DLQ has {failed_count} failed messages (critical threshold).",
                        fix_suggestion="Review failed messages in settings.",
                    )
                return HealthReport(
                    component_name="DLQ",
                    status="pass",
                    code="OK_DLQ_HEALTHY",
                    meta_data={"failed_count": failed_count},
                    message="Message delivery is healthy.",
                    detail=f"DLQ has {failed_count} failed message(s).",
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
                detail=f"DLQ health check error: {e}",
            )


class ServerDiagnosticsManager:
    """Manages and executes all Server-level business diagnostics."""

    def __init__(self) -> None:
        self._probes: list[DiagnosticProtocol] = [
            DLQDiagnostic(),
            # Future probes (e.g., Connection Pools, Token Limiters) can be added here
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
