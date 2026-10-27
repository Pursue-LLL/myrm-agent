"""Deliverables: what the answer hands over, whether the run wrote it, and how much backs it.

[INPUT]
- .auto_staging::stage_unwritten_deliverables, StagedArtifactMeta (POS: save unwritten drafts into the workspace when the guard lets the run finish)
- .confidence_tier::DeliverableConfidenceTier, DeliverableTierEvidence, DeliverableTierMetadata, resolve_deliverable_tier, should_disclose_tier (POS: the evidence tier a delivery earns and when to show it)
- .write_verifier::UnwrittenDeliverable, check_deliverable_write_claim, check_unwritten_deliverables (POS: a claimed or implied save the run never made)

[OUTPUT]
- StagedArtifactMeta, stage_unwritten_deliverables, DeliverableConfidenceTier, DeliverableTierEvidence, DeliverableTierMetadata, resolve_deliverable_tier, should_disclose_tier, UnwrittenDeliverable, check_deliverable_write_claim, check_unwritten_deliverables

[POS]
Public surface of the deliverable package, consulted by the completion guard and by the per-turn disclosure.
"""

from myrm_agent_harness.agent.middlewares.completion.deliverable.auto_staging import (
    StagedArtifactMeta,
    stage_unwritten_deliverables,
)
from myrm_agent_harness.agent.middlewares.completion.deliverable.confidence_tier import (
    DeliverableConfidenceTier,
    DeliverableTierEvidence,
    DeliverableTierMetadata,
    resolve_deliverable_tier,
    should_disclose_tier,
)
from myrm_agent_harness.agent.middlewares.completion.deliverable.write_verifier import (
    UnwrittenDeliverable,
    check_deliverable_write_claim,
    check_unwritten_deliverables,
)

__all__ = [
    "DeliverableConfidenceTier",
    "DeliverableTierEvidence",
    "DeliverableTierMetadata",
    "StagedArtifactMeta",
    "UnwrittenDeliverable",
    "check_deliverable_write_claim",
    "check_unwritten_deliverables",
    "resolve_deliverable_tier",
    "should_disclose_tier",
    "stage_unwritten_deliverables",
]
