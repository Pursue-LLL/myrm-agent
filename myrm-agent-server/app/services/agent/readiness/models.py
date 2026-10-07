"""Readiness report data model: levels, finding codes, items and the aggregated report.

[INPUT]
- (stdlib only) (POS: plain data, no service dependencies)

[OUTPUT]
- ReadinessLevel: ready / warning / blocked
- ReadinessCode: stable identifier of each finding; clients localize it (``reason`` stays English)
- AgentReadinessItem: single-dimension check result
- AgentReadinessReport: aggregated per-agent report and its API wire shape (``to_dict``)

[POS]
Business-layer wire contract of the per-agent readiness dry-run. The checks that produce these
values live in resolver.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, StrEnum


class ReadinessLevel(str, Enum):
    READY = "ready"
    WARNING = "warning"
    BLOCKED = "blocked"


class ReadinessCode(StrEnum):
    """What a finding is about. Clients map it to localized copy."""

    MODEL_NOT_READY = "model_not_ready"
    AGENT_NOT_FOUND = "agent_not_found"
    MCP_NOT_ENABLED = "mcp_not_enabled"
    MCP_NOT_FOUND = "mcp_not_found"
    MCP_MISSING_SECRETS = "mcp_missing_secrets"
    SKILLS_MISSING = "skills_missing"
    TOOLS_NONE_ENABLED = "tools_none_enabled"
    SEARCH_NOT_CONFIGURED = "search_not_configured"
    COMPUTER_USE_IN_SANDBOX = "computer_use_in_sandbox"
    LOCAL_SKILLS_UNAVAILABLE = "local_skills_unavailable"


@dataclass(frozen=True, slots=True)
class AgentReadinessItem:
    """Single dimension check result.

    ``reason`` / ``next_action`` are English diagnostics for logs and API consumers. User-facing
    clients render ``code`` instead, filling in ``names`` (servers, secret keys) and ``count``
    (how many things are affected; skills are counted, not named, because their ids are internal).
    """

    dimension: str
    level: ReadinessLevel
    code: ReadinessCode
    reason: str
    next_action: str
    settings_path: str
    names: tuple[str, ...] = ()
    count: int = 0


@dataclass(frozen=True, slots=True)
class AgentReadinessReport:
    """Aggregated per-agent readiness report."""

    overall_level: ReadinessLevel
    items: tuple[AgentReadinessItem, ...]
    agent_id: str
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "overall_level": self.overall_level.value,
            "items": [
                {
                    "dimension": item.dimension,
                    "level": item.level.value,
                    "code": item.code.value,
                    "reason": item.reason,
                    "next_action": item.next_action,
                    "settings_path": item.settings_path,
                    "names": list(item.names),
                    "count": item.count,
                }
                for item in self.items
            ],
            "agent_id": self.agent_id,
            "checked_at": self.checked_at,
        }
