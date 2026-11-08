"""Domain models of two-layer context injection and multi-pass dialectic reconciliation.

[INPUT]
None (pure domain models).

[OUTPUT]
DialecticReasoningLevel, DialecticPassKind, DialecticCadenceConfig, DialecticReconciliationConfig,
BaseContextBundle, BaseContextPayload, ConflictItem, DialecticConflictCandidate,
DialecticReconciliationResult, TwoLayerContextInjectionResult.

[POS]
Data structures shared by the two-layer context injector and the dialectic reconcilers.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class DialecticReasoningLevel(StrEnum):
    """Reasoning compute allocation for dialectic synthesis passes."""

    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"


class DialecticPassKind(StrEnum):
    """Reasoning pass stages in dialectic loop."""

    INSPECTION = "inspection"
    SYNTHESIS = "synthesis"
    RECONCILIATION = "reconciliation"


@dataclass(frozen=True)
class DialecticCadenceConfig:
    """Three orthogonal control knobs balancing latency, cost, and reconciliation depth.

    Attributes:
        context_cadence: Refresh interval in turns for Layer 1 Base Context.
        dialectic_cadence: Turn interval for automated dialectic conflict checks.
        dialectic_depth: Number of passes in dialectic reconciliation (1-3).
        dialectic_reasoning_level: Model reasoning tier to allocate.
        conflict_similarity_cutoff: Similarity and conflict threshold.
    """

    context_cadence: int = 5
    dialectic_cadence: int = 3
    dialectic_depth: int = 2
    dialectic_reasoning_level: DialecticReasoningLevel = DialecticReasoningLevel.STANDARD
    conflict_similarity_cutoff: float = 0.65


DialecticReconciliationConfig = DialecticCadenceConfig


@dataclass
class BaseContextBundle:
    """Layer 1: low-frequency base context snapshot.

    Injected at the tail of the user message to protect the system prompt KV cache.
    """

    session_summary: str = ""
    standing_peer_cards: list[str] = field(default_factory=list)
    cache_control_hash: str = ""
    refreshed_at_turn: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


BaseContextPayload = BaseContextBundle


@dataclass
class ConflictItem:
    """Two memory statements that contradict each other."""

    statement_a: str = ""
    statement_b: str = ""
    subject_domain: str = ""
    conflict_score: float = 1.0


DialecticConflictCandidate = ConflictItem


@dataclass
class DialecticReconciliationResult:
    """Layer 2: outcome of reconciling one contradiction."""

    passes_executed: list[DialecticPassKind] = field(default_factory=list)
    resolved_statement: str = ""
    superseded_statements: list[str] = field(default_factory=list)
    confidence: float = 1.0
    rationale: str = ""


@dataclass
class TwoLayerContextInjectionResult:
    """Assembled Layer 1 base context and Layer 2 dialectic block for one turn."""

    layer1_base_context: str = ""
    layer2_dialectic_block: str = ""
    injected_position: str = "user_message_tail"
    is_cache_safe: bool = True
    token_overhead: int = 0
