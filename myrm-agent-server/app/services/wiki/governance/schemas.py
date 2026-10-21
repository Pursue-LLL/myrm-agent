"""Knowledge governance schemas and data contracts.

[INPUT]
- None (pure domain dataclasses)

[OUTPUT]
- ExpiringConceptInfo: Metadata for concepts approaching expiration or stale state.
- GovernanceOverviewResult: Container for four-queue governance workbench (pending, expiring, gaps, archived).
- GovernanceExtendRequest / GovernanceArchiveRequest / GovernanceReviveRequest: Request DTOs.
- GovernanceActionResult: Standardized action result with undo capability.

[POS]
Domain contract for KnowledgeGovernanceWorkbenchExpiryArchiveRevival.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExpiringConceptInfo:
    """Metadata for concepts approaching expiration or marked stale."""

    concept_name: str
    relative_path: str
    age_days: int
    modified_at_iso: str
    is_permanent: bool = False
    hit_count: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "concept_name": self.concept_name,
            "relative_path": self.relative_path,
            "age_days": self.age_days,
            "modified_at_iso": self.modified_at_iso,
            "is_permanent": self.is_permanent,
            "hit_count": self.hit_count,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class GovernanceOverviewResult:
    """Four-queue governance workbench aggregation result."""

    pending_count: int
    expiring_count: int
    gaps_count: int
    archived_count: int
    total_active: int
    expiring_concepts: list[ExpiringConceptInfo] = field(default_factory=list)
    archived_concepts: list[ExpiringConceptInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "pending_count": self.pending_count,
            "expiring_count": self.expiring_count,
            "gaps_count": self.gaps_count,
            "archived_count": self.archived_count,
            "total_active": self.total_active,
            "expiring_concepts": [c.to_dict() for c in self.expiring_concepts],
            "archived_concepts": [c.to_dict() for c in self.archived_concepts],
        }


@dataclass(frozen=True, slots=True)
class GovernanceActionResult:
    """Result of governance operations with optional undo token."""

    success: bool
    affected_count: int
    message: str
    undo_token: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "affected_count": self.affected_count,
            "message": self.message,
            "undo_token": self.undo_token,
        }
