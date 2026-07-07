"""Tenant Guardrail Policy Provider.

Placeholder for future SaaS tenant-specific tool policies. Subagent access is gated
by Work Unit balance via PlatformBudgetAdapter, not by this provider.
"""

import logging

from myrm_agent_harness.agent.middlewares.guardrails.core import (
    GuardrailDecision,
    GuardrailProvider,
    GuardrailRequest,
)

logger = logging.getLogger(__name__)


class TenantPolicyProvider(GuardrailProvider):
    """Reserved hook for SaaS tenant tool policies."""

    name = "tenant_policy"

    async def aevaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        return GuardrailDecision(allow=True)

    def evaluate(self, request: GuardrailRequest) -> GuardrailDecision:
        import asyncio

        return asyncio.run(self.aevaluate(request))
