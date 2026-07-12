"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: health report model)
- app.platform_utils.deployment_capabilities::get_deployment_capabilities (POS: deploy mode flags)

[OUTPUT]
- present_health_report: deployment-aware HealthReport for WebUI payloads

[POS]
Adjusts user-facing health fields per deploy mode without changing harness probe facts.
"""

from __future__ import annotations

from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.platform_utils.deployment_capabilities import get_deployment_capabilities

_PLATFORM_MANAGED_FIX = "Resource limits are managed by the hosting platform."


def present_health_report(report: HealthReport) -> HealthReport:
    """Adjust user-facing fields for deployment context without changing probe facts."""
    caps = get_deployment_capabilities()
    if not caps.is_sandbox_instance or report.component_name != "SystemResources":
        return report
    if not report.fix_suggestion:
        return report
    return report.model_copy(update={"fix_suggestion": _PLATFORM_MANAGED_FIX})
