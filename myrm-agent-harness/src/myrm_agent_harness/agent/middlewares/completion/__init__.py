"""Completion guard subsystem — finish gate, verification, and deliverable checks.

[INPUT]
- .completion_guard::CompletionGuard, classify_verification, reset_completion_guard, build_checklist, is_mutating_tool, attach_disclosure_to_event (POS: the finish gate package: gate, checklist, verification classifier, tool safety, per-turn disclosure)
- .deliverable::stage_unwritten_deliverables, StagedArtifactMeta, DeliverableConfidenceTier, DeliverableTierEvidence, DeliverableTierMetadata, resolve_deliverable_tier, UnwrittenDeliverable, check_deliverable_write_claim, check_unwritten_deliverables (POS: deliverables: staging, evidence tier, unwritten-deliverable checks)
- .execution_claim::check_execution_claim (POS: completion-claim grounding against this run's tool records)
- .query_grounding_verifier::check_query_grounding_claim, detect_entity_query_intent, has_successful_query_evidence (POS: query grounding verification)

[OUTPUT]
- CompletionGuard, build_checklist, classify_verification, is_mutating_tool, resolve_deliverable_tier, check_query_grounding_claim, check_execution_claim, attach_disclosure_to_event, stage_unwritten_deliverables

[POS]
Completion Guard 完成门禁子系统入口。确保智能体在具备验证、交付物证据与实体接地证据的前提下安全结束。
"""

from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    attach_disclosure_to_event,
    build_checklist,
    classify_verification,
    is_mutating_tool,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.completion.deliverable import (
    DeliverableConfidenceTier,
    DeliverableTierEvidence,
    DeliverableTierMetadata,
    StagedArtifactMeta,
    UnwrittenDeliverable,
    check_deliverable_write_claim,
    check_unwritten_deliverables,
    resolve_deliverable_tier,
    stage_unwritten_deliverables,
)
from myrm_agent_harness.agent.middlewares.completion.execution_claim import check_execution_claim
from myrm_agent_harness.agent.middlewares.completion.query_grounding_verifier import (
    check_query_grounding_claim,
    detect_entity_query_intent,
    has_successful_query_evidence,
    is_honest_negative_or_clarification,
)

__all__ = [
    "CompletionGuard",
    "DeliverableConfidenceTier",
    "DeliverableTierEvidence",
    "DeliverableTierMetadata",
    "StagedArtifactMeta",
    "UnwrittenDeliverable",
    "attach_disclosure_to_event",
    "build_checklist",
    "check_deliverable_write_claim",
    "check_execution_claim",
    "check_query_grounding_claim",
    "check_unwritten_deliverables",
    "classify_verification",
    "detect_entity_query_intent",
    "has_successful_query_evidence",
    "is_honest_negative_or_clarification",
    "is_mutating_tool",
    "reset_completion_guard",
    "resolve_deliverable_tier",
    "stage_unwritten_deliverables",
]
