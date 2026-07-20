"""Unit tests for tenant guardrail delegation entitlement checks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.guardrails.core import GuardrailRequest
from myrm_agent_harness.agent.sub_agents.types import DELEGATION_CAPABILITY_MANIFEST

from app.services.security.tenant_guardrail import TenantPolicyProvider

_CAPS_FN = "app.platform_utils.deployment_capabilities.get_deployment_capabilities"
_FETCH_FN = "app.platform_utils.sandbox.entitlements.entitlement_guard.fetch_sandbox_entitlements"


def _make_caps(uses_cp: bool) -> MagicMock:
    caps = MagicMock()
    caps.uses_cp_entitlements = uses_cp
    return caps


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    DELEGATION_CAPABILITY_MANIFEST.orchestrator_child_tools,
)
async def test_allows_orchestrator_delegation_tools_regardless_of_enable_subagent_flag(
    tool_name: str,
) -> None:
    mock_entitlement = MagicMock()
    mock_entitlement.enable_subagent = False

    with (
        patch(_CAPS_FN, return_value=_make_caps(uses_cp=True)),
        patch(_FETCH_FN, return_value=mock_entitlement),
    ):
        decision = await TenantPolicyProvider().aevaluate(
            GuardrailRequest(tool_name=tool_name, tool_input={}),
        )

    assert decision.allow is True


@pytest.mark.asyncio
async def test_skips_entitlement_check_in_local_mode() -> None:
    with patch(_CAPS_FN, return_value=_make_caps(uses_cp=False)):
        decision = await TenantPolicyProvider().aevaluate(
            GuardrailRequest(tool_name="delegate_task_tool", tool_input={}),
        )

    assert decision.allow is True
