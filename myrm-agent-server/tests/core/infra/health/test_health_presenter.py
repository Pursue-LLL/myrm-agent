"""Tests for sandbox-aware health report presentation."""

from __future__ import annotations

from unittest.mock import patch

from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.core.infra.health.health_presenter import present_health_report
from app.platform_utils.deployment_capabilities import DeploymentCapabilities


def _sandbox_caps() -> DeploymentCapabilities:
    return DeploymentCapabilities(
        allows_local_skills=False,
        requires_api_key_auth=True,
        uses_platform_budget=True,
        validates_mcp_response_size=True,
        uses_config_encryption=True,
        requires_strict_ws_auth=True,
        uses_cp_entitlements=True,
        trust_cp_proxy_identity=True,
        enables_auth_audit=True,
        default_metrics_enabled=True,
        runs_sandbox_startup_validation=True,
        skips_webui_model_preflight=True,
        is_sandbox_instance=True,
    )


def test_sandbox_system_resources_fix_suggestion_rewritten() -> None:
    report = HealthReport(
        component_name="SystemResources",
        status="warn",
        message="CPU high",
        fix_suggestion="Close unused applications to free memory.",
    )
    with patch(
        "app.core.infra.health.health_presenter.get_deployment_capabilities",
        return_value=_sandbox_caps(),
    ):
        presented = present_health_report(report)
    assert presented.fix_suggestion == "Resource limits are managed by the hosting platform."


def _local_caps() -> DeploymentCapabilities:
    return DeploymentCapabilities(
        allows_local_skills=True,
        requires_api_key_auth=False,
        uses_platform_budget=False,
        validates_mcp_response_size=False,
        uses_config_encryption=False,
        requires_strict_ws_auth=False,
        uses_cp_entitlements=False,
        trust_cp_proxy_identity=False,
        enables_auth_audit=False,
        default_metrics_enabled=False,
        runs_sandbox_startup_validation=False,
        skips_webui_model_preflight=False,
        is_sandbox_instance=False,
    )


def test_local_system_resources_unchanged() -> None:
    report = HealthReport(
        component_name="SystemResources",
        status="warn",
        message="CPU high",
        fix_suggestion="Close unused applications.",
    )
    with patch(
        "app.core.infra.health.health_presenter.get_deployment_capabilities",
        return_value=_local_caps(),
    ):
        presented = present_health_report(report)
    assert presented.fix_suggestion == "Close unused applications."
