"""Two-layer context injection and multi-pass dialectic reconciliation.

[INPUT]
models.py, injector.py, dialectic_engine.py

[OUTPUT]
Public exports of the two-layer context injector, the dialectic reconciliation engine and their models.

[POS]
Package facade of the two-layer context injection suite.
"""

from myrm_agent_harness.toolkits.memory.two_layer_dialectic.dialectic_engine import (
    DialecticReconciliationEngine,
)
from myrm_agent_harness.toolkits.memory.two_layer_dialectic.injector import (
    TwoLayerContextInjector,
)
from myrm_agent_harness.toolkits.memory.two_layer_dialectic.models import (
    BaseContextBundle,
    BaseContextPayload,
    ConflictItem,
    DialecticCadenceConfig,
    DialecticConflictCandidate,
    DialecticPassKind,
    DialecticReasoningLevel,
    DialecticReconciliationConfig,
    DialecticReconciliationResult,
    TwoLayerContextInjectionResult,
)

MultiPassDialecticReconciler = DialecticReconciliationEngine

__all__ = [
    "BaseContextBundle",
    "BaseContextPayload",
    "ConflictItem",
    "DialecticCadenceConfig",
    "DialecticConflictCandidate",
    "DialecticPassKind",
    "DialecticReasoningLevel",
    "DialecticReconciliationConfig",
    "DialecticReconciliationEngine",
    "DialecticReconciliationResult",
    "MultiPassDialecticReconciler",
    "TwoLayerContextInjectionResult",
    "TwoLayerContextInjector",
]
