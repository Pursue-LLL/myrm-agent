"""Derive enable_web_fetch from Agent Security capability overrides.

[INPUT]
- GeneralAgentParams.agent_security_raw (capabilities list from profile)

[OUTPUT]
- resolve_enable_web_fetch: bool gate for web_fetch_tool Turn1 bind

[POS]
Shared server helper so Web, Channel, Cron, Kanban, Eval, and Voice entry points apply the
same net_fetch capability gate without duplicating parsing logic.
"""

from __future__ import annotations


def resolve_enable_web_fetch(agent_security_raw: dict[str, object] | None) -> bool:
    """Disable fetch when agent security explicitly omits net_fetch capability."""
    if not agent_security_raw:
        return True
    caps = agent_security_raw.get("capabilities")
    if not isinstance(caps, list) or not caps:
        return True
    normalized = [str(c).strip() for c in caps if isinstance(c, str) and str(c).strip()]
    if not normalized:
        return True
    return "net_fetch" in normalized
