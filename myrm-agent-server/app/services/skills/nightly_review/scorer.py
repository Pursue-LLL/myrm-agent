"""Collaboration scoring over ledger negative events (pure, deterministic).

[INPUT]
- Negative event dicts (event_type, entity_id, summary, created_at)

[OUTPUT]
- NightlyFinding: per-entity cluster with category, count, recommendation

[POS]
Rules-only 360° signal. No LLM calls, no scoring of prose — counts and
thresholds only. Findings feed the regression ledger, never auto-remediation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NightlyFinding:
    """One collaboration finding for an entity (agent or skill)."""

    entity_type: str
    entity_id: str
    category: str
    count: int
    recommendation: str
    evidence_count: int


_APPROVAL_RETURN_TYPES = frozenset(
    {
        "review.rejected",
        "evolution.rejected",
        "skill_growth.rejected",
    }
)

_TOOL_ERROR_TYPES = frozenset(
    {
        "evolution.apply_failed",
        "skill_growth.failed_scan",
        "skill_growth.blocked",
    }
)

_MIN_COUNT = 3


def _categorize(event_type: str) -> str | None:
    if event_type in _APPROVAL_RETURN_TYPES:
        return "approval_return"
    if event_type in _TOOL_ERROR_TYPES:
        return "tool_error"
    return None


def _recommendation(category: str) -> str:
    if category == "approval_return":
        return "review-reject-loop"
    return "tool-error-cluster"


def score_day(
    events: list[dict[str, object]],
    *,
    min_count: int = _MIN_COUNT,
) -> list[NightlyFinding]:
    """Cluster negative events per entity; emit findings above threshold."""
    clusters: Counter[tuple[str, str, str]] = Counter()
    for event in events:
        event_type = str(event.get("event_type") or "")
        category = _categorize(event_type)
        if category is None:
            continue
        entity_type = str(event.get("entity_type") or "unknown")
        entity_id = str(event.get("entity_id") or "unknown")
        clusters[(entity_type, entity_id, category)] += 1
    findings = [
        NightlyFinding(
            entity_type=entity_type,
            entity_id=entity_id,
            category=category,
            count=count,
            recommendation=_recommendation(category),
            evidence_count=count,
        )
        for (entity_type, entity_id, category), count in clusters.items()
        if count >= min_count
    ]
    findings.sort(key=lambda finding: (-finding.count, finding.entity_id))
    return findings
