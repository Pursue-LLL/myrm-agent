"""Tenant Guardrail Policy Provider.

Enforces SaaS quota and tenant restrictions for tools.
"""

import logging
from typing import Any

from myrm_agent_harness.agent.middlewares.guardrails.core import (
    GuardrailDecision,
    GuardrailProvider,
    GuardrailReason,
    GuardrailRequest,
)

logger = logging.getLogger(__name__)


class TenantPolicyProvider(GuardrailProvider):
    """Enforces SaaS quotas and tenant-specific boundaries."""
    
    name = "tenant_policy"

    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        from app.platform_utils.deployment_capabilities import get_deployment_capabilities
        
        # If not in SaaS/entitlement mode, skip
        if not get_deployment_capabilities().uses_cp_entitlements:
            return GuardrailDecision(allow=True)
            
        try:
            from app.platform_utils.sandbox.entitlements.entitlement_guard import fetch_sandbox_entitlements
            entitlements = fetch_sandbox_entitlements()
            if not entitlements:
                return GuardrailDecision(allow=True)
                
            # Here we would query the actual quota usage from the control plane
            # For now, we just pass through or enforce static entitlement rules
            # Example: Block subagents if not entitled
            if request.tool_name == "spawn_subagent_tool" and not entitlements.enable_subagent:
                return GuardrailDecision(
                    allow=False,
                    reasons=[
                        GuardrailReason(
                            code="tenant.entitlement_blocked",
                            message="Your current plan does not support spawning subagents. Please upgrade your plan."
                        )
                    ]
                )
            
            return GuardrailDecision(allow=True)
        except Exception as exc:
            logger.warning("Tenant Guardrail check failed (fail-open): %s", exc)
            return GuardrailDecision(allow=True)

    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        import asyncio
        return asyncio.run(self.aevaluate(request))
