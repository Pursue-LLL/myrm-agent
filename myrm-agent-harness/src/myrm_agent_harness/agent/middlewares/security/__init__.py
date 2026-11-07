"""Security enforcement middleware — boundary rules and multi-layer defense.

[INPUT]
- agent.security.detection.content_boundary (boundary tags)
- agent.security.detection.leak_detector / prompt_guard / pii (defense layers)
- agent.middlewares._session_context (canary, privacy policy, terminal errors)

[OUTPUT]
- SecurityBoundaryMiddleware: SECURITY_BOUNDARY_SYSTEM_RULES injection
- CanaryMiddleware: session canary instruction, behind the user's input
- SecurityGuardrailMiddleware: eight-layer defense middleware
"""

from myrm_agent_harness.agent.middlewares.security.canary_middleware import CanaryMiddleware
from myrm_agent_harness.agent.middlewares.security.security_boundary_middleware import (
    SecurityBoundaryMiddleware,
)
from myrm_agent_harness.agent.middlewares.security.security_guardrail_middleware import (
    SecurityGuardrailMiddleware,
)

__all__ = ["CanaryMiddleware", "SecurityBoundaryMiddleware", "SecurityGuardrailMiddleware"]
