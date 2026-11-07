"""Domain models for cross-cycle pattern discovery.

[INPUT]
- (none)

[OUTPUT]
- PatternDurability: How stable a discovered pattern is over time
- DiscoveredPattern: A single behavioral or knowledge pattern with its evidence
- PatternDiscoveryResponse: Structured LLM output for pattern discovery
- PatternReport: Immutable result of a pattern discovery cycle

[POS]
Domain models and result DTO for pattern discovery. The LLM-facing models accept natural
field-name aliases so structured parsing survives naming drift.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pydantic import AliasChoices, BaseModel, Field


class PatternDurability(StrEnum):
    """How stable a discovered pattern is over time."""

    EMERGING = "emerging"
    ESTABLISHED = "established"
    DECLINING = "declining"


class DiscoveredPattern(BaseModel):
    """A single behavioral or knowledge pattern found across memory cycles."""

    title: str = Field(
        validation_alias=AliasChoices("title", "category"),
        description="Short pattern name (< 60 chars)",
    )
    description: str = Field(description="What this pattern means for the user")
    evidence_summary: str = Field(
        validation_alias=AliasChoices("evidence_summary", "evidence"),
        description="Key memories or events supporting this pattern",
    )
    durability: PatternDurability = Field(default=PatternDurability.EMERGING)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    actionable_suggestion: str = Field(
        default="",
        validation_alias=AliasChoices("actionable_suggestion", "suggestion"),
        description="Optional proactive suggestion the agent can surface to the user",
    )


class PatternDiscoveryResponse(BaseModel):
    """Structured LLM output for pattern discovery."""

    patterns: list[DiscoveredPattern] = Field(default_factory=list)
    meta_observation: str = Field(
        default="",
        description="High-level observation about the user's overall behavior trajectory",
    )


@dataclass(frozen=True)
class PatternReport:
    """Immutable result of a pattern discovery cycle."""

    patterns: tuple[DiscoveredPattern, ...] = ()
    meta_observation: str = ""
    memory_count: int = 0
    insight_count: int = 0
    duration_ms: float = 0.0
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "patterns": [p.model_dump() for p in self.patterns],
            "meta_observation": self.meta_observation,
            "memory_count": self.memory_count,
            "insight_count": self.insight_count,
            "duration_ms": self.duration_ms,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }

    @property
    def has_patterns(self) -> bool:
        return len(self.patterns) > 0


__all__ = [
    "DiscoveredPattern",
    "PatternDiscoveryResponse",
    "PatternDurability",
    "PatternReport",
]
