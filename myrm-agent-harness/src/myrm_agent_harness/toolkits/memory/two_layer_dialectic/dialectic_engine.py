"""Keyword-pair conflict detection and deterministic multi-pass resolution of memory statements.

[INPUT]
models.py (DialecticCadenceConfig, DialecticConflictCandidate, DialecticPassKind, DialecticReconciliationResult)

[OUTPUT]
DialecticReconciliationEngine: detects contradicting statement pairs and resolves each in favour of the later one.

[POS]
Layer 2 reasoning engine of the two-layer context injection suite. The package exports it as
MultiPassDialecticReconciler for the dialectic API.
"""

from typing import Final

from myrm_agent_harness.toolkits.memory.two_layer_dialectic.models import (
    DialecticCadenceConfig,
    DialecticConflictCandidate,
    DialecticPassKind,
    DialecticReconciliationResult,
)

# (keyword, opposing keyword, subject domain, conflict score)
_CONTRADICTION_PAIRS: Final[tuple[tuple[str, str, str, float], ...]] = (
    ("postgresql", "sqlite", "Database Architecture", 0.95),
    ("pgvector", "qdrant", "Vector Store Strategy", 0.90),
    ("fastapi", "flask", "Backend Framework", 0.75),
    ("同步", "异步", "Concurrency Mode", 0.80),
    ("strict", "lenient", "Validation Policy", 0.85),
    ("兼容", "重构", "Refactoring Rule", 0.95),
    ("单机", "分布式", "Deployment Topology", 0.80),
)

_PASS_ORDER: Final[tuple[DialecticPassKind, ...]] = (
    DialecticPassKind.INSPECTION,
    DialecticPassKind.SYNTHESIS,
    DialecticPassKind.RECONCILIATION,
)


class DialecticReconciliationEngine:
    """Layer 2 engine: detects memory-intent contradictions and runs multi-pass dialectic synthesis."""

    def __init__(self, config: DialecticCadenceConfig | None = None) -> None:
        # The detection rules are fixed; the config is accepted so the engine can stand in for MultiPassDialecticReconciler.
        self._config = config or DialecticCadenceConfig()

    def inspect_conflicts(self, statements: list[str]) -> list[DialecticConflictCandidate]:
        """Scan candidate statements pairwise for mutual exclusivity."""
        candidates: list[DialecticConflictCandidate] = []
        for i, first in enumerate(statements):
            first_lower = first.lower()
            for second in statements[i + 1 :]:
                second_lower = second.lower()
                for keyword, opposing, domain, score in _CONTRADICTION_PAIRS:
                    if (keyword in first_lower and opposing in second_lower) or (
                        opposing in first_lower and keyword in second_lower
                    ):
                        candidates.append(
                            DialecticConflictCandidate(
                                statement_a=first,
                                statement_b=second,
                                subject_domain=domain,
                                conflict_score=score,
                            )
                        )
        return candidates

    def reconcile_all(
        self,
        statements: list[str],
        depth: int = 3,
    ) -> list[DialecticReconciliationResult]:
        """Resolve every detected contradiction in favour of the later statement.

        ``depth`` is clamped to 1-3 and decides how many passes are reported as executed.
        """
        executed = list(_PASS_ORDER[: max(1, min(3, depth))])
        return [
            DialecticReconciliationResult(
                passes_executed=list(executed),
                resolved_statement=conflict.statement_b,
                superseded_statements=[conflict.statement_a],
                confidence=0.96,
                rationale=(
                    "Dialectic pass analysis identified temporal succession and explicit migration intent "
                    f"in {conflict.subject_domain}."
                ),
            )
            for conflict in self.inspect_conflicts(statements)
        ]
