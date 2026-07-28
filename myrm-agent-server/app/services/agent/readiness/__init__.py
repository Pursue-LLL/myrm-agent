"""Agent readiness checking — per-agent configuration dry-run.

[OUTPUT]
- ReadinessLevel: three-tier enum (ready / warning / blocked)
- AgentReadinessItem: single dimension check result
- AgentReadinessReport: aggregated per-agent readiness report
- resolve_agent_readiness: async resolver
- get_readiness_resolver: global singleton accessor

[POS]
Business-layer per-agent readiness resolver. Checks model, MCP, skills, tools,
search, and deployment dimensions against an agent's ResolvedAgentProfile.
Extends the global /config/readiness (provider+search) to agent-specific scope.
"""

from app.services.agent.readiness.resolver import (
    AgentReadinessItem,
    AgentReadinessReport,
    ReadinessLevel,
    get_readiness_resolver,
    resolve_agent_readiness,
)

__all__ = [
    "AgentReadinessItem",
    "AgentReadinessReport",
    "ReadinessLevel",
    "get_readiness_resolver",
    "resolve_agent_readiness",
]
