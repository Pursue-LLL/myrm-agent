"""[INPUT]
- myrm_agent_harness.observability.diagnostics.manager::run_all_diagnostics (POS: diagnostic hook runner)
- myrm_agent_harness.api.hooks::get_terminal_errors (POS: terminal error registry)
- app.core.infra.health.server_diagnostics::run_server_diagnostics (POS: server-layer probes)

[OUTPUT]
- HealthSnapshot: frozen harness + server HealthReport bundles
- collect_health_snapshot: side-effect-free diagnostic collection

[POS]
Pure health data collection for /health/doctor and the background history recorder.
"""

from __future__ import annotations

from dataclasses import dataclass

from myrm_agent_harness.api.hooks import get_terminal_errors
from myrm_agent_harness.observability.diagnostics.manager import run_all_diagnostics
from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.core.infra.health.server_diagnostics import run_server_diagnostics


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    """Immutable bundle of diagnostic reports from harness and server layers."""

    harness_reports: tuple[HealthReport, ...]
    server_reports: tuple[HealthReport, ...]


async def collect_health_snapshot() -> HealthSnapshot:
    """Run all diagnostics and return reports without publishing alerts."""
    harness_reports: list[HealthReport] = list(await run_all_diagnostics())

    registry = get_terminal_errors()
    errors = list(registry.get_all())
    if errors:
        harness_reports.append(
            HealthReport(
                component_name="AgentEngine",
                status="fail",
                message="Agent engine has encountered a critical error.",
                detail=f"Terminal error detected: {'; '.join(errors)}",
                fix_suggestion="Try restarting the application.",
            )
        )
    elif not any(r.component_name == "AgentEngine" for r in harness_reports):
        harness_reports.append(
            HealthReport(
                component_name="AgentEngine",
                status="pass",
                message="Agent engine is running normally.",
            )
        )

    server_reports = list(await run_server_diagnostics())
    return HealthSnapshot(
        harness_reports=tuple(harness_reports),
        server_reports=tuple(server_reports),
    )
