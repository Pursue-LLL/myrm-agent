"""Tests for sandbox-aware recovery action URLs."""

from __future__ import annotations

from unittest.mock import patch

from myrm_agent_harness.toolkits.llms.errors import FailoverReason

from app.core.errors.llm_errors import generate_recovery_actions
from app.platform_utils.deployment_capabilities import DeploymentCapabilities


def test_billing_recovery_top_up_points_to_subscription_in_sandbox() -> None:
    sandbox_caps = DeploymentCapabilities(
        allows_local_skills=False,
        requires_api_key_auth=True,
        uses_platform_budget=True,
        validates_mcp_response_size=True,
        uses_config_encryption=True,
        requires_strict_ws_auth=True,
        uses_cp_entitlements=True,
        trust_cp_proxy_identity=True,
        enables_auth_audit=True,
        default_metrics_enabled=False,
        runs_sandbox_startup_validation=True,
        skips_webui_model_preflight=True,
        is_sandbox_instance=True,
    )
    with patch(
        "app.core.errors.llm_errors.get_deployment_capabilities",
        return_value=sandbox_caps,
    ):
        actions = generate_recovery_actions(FailoverReason.BILLING, "en")

    top_up = next(action for action in actions if action["id"] == "top_up")
    assert top_up["url"] == "/subscription"


def test_billing_recovery_top_up_points_to_pricing_in_local() -> None:
    local_caps = DeploymentCapabilities(
        allows_local_skills=True,
        requires_api_key_auth=False,
        uses_platform_budget=False,
        validates_mcp_response_size=False,
        uses_config_encryption=False,
        requires_strict_ws_auth=False,
        uses_cp_entitlements=False,
        trust_cp_proxy_identity=False,
        enables_auth_audit=False,
        default_metrics_enabled=True,
        runs_sandbox_startup_validation=False,
        skips_webui_model_preflight=False,
        is_sandbox_instance=False,
    )
    with patch(
        "app.core.errors.llm_errors.get_deployment_capabilities",
        return_value=local_caps,
    ):
        actions = generate_recovery_actions(FailoverReason.BILLING, "en")

    top_up = next(action for action in actions if action["id"] == "top_up")
    assert top_up["url"] == "/pricing"


def test_provider_policy_blocked_recovery_actions_en_and_zh() -> None:
    actions_en = generate_recovery_actions(FailoverReason.PROVIDER_POLICY_BLOCKED, "en")
    action_ids_en = [a["id"] for a in actions_en]
    assert action_ids_en == ["switch_to_api_key", "switch_model"]
    assert actions_en[0]["label"] == "Switch to API Key"
    assert actions_en[0]["url"] == "/settings/models"
    assert actions_en[1]["label"] == "Switch Model"
    assert actions_en[1]["url"] == "/settings/models"

    actions_zh = generate_recovery_actions(FailoverReason.PROVIDER_POLICY_BLOCKED, "zh")
    assert actions_zh[0]["label"] == "改用 API Key"
    assert actions_zh[1]["label"] == "切换模型"


def test_long_context_tier_recovery_actions() -> None:
    actions_en = generate_recovery_actions(FailoverReason.LONG_CONTEXT_TIER, "en")
    action_ids_en = [a["id"] for a in actions_en]
    assert action_ids_en == ["switch_to_api_key", "start_new_chat", "switch_model"]
    assert actions_en[0]["label"] == "Switch to API Key"
    assert actions_en[1]["label"] == "New Chat"
    assert actions_en[1]["url"] == "/"
    assert actions_en[2]["label"] == "Switch Model"
