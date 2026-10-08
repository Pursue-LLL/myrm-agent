"""Service provider for Conclusion Attribution & Chat Evidence.

[POS]
Maintains singleton ConclusionEvidenceSuite instance and bridges Harness execution
with Server DTO schemas.

[INPUT]
- myrm_agent_harness.toolkits.memory (ConclusionEvidenceSuite, AttributedConclusion,
  AttributionLevel, ChatEvidenceBundle, MessageEvidenceItem, ToolCallEvidenceItem,
  DerivationTraversalView, ConclusionEvidenceStats, DerivationCycleError)
- app.schemas.conclusion_evidence

[OUTPUT]
- get_conclusion_evidence_suite, reset_conclusion_evidence_suite
- execute_create_conclusion, query_conclusion, query_premises, query_derivatives
- query_two_way_traversal, execute_chat_with_evidence, get_evidence_stats
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    AttributedConclusion,
    AttributionLevel,
    ChatEvidenceBundle,
    ConclusionEvidenceStats,
    ConclusionEvidenceSuite,
    DerivationTraversalView,
)

from app.schemas.conclusion_evidence import (
    AttributedConclusionDTO,
    ChatEvidenceBundleDTO,
    ChatWithEvidenceRequestDTO,
    ChatWithEvidenceResponseDTO,
    ConclusionEvidenceStatsDTO,
    CreateAttributedConclusionDTO,
    DerivationTraversalViewDTO,
    MessageEvidenceItemDTO,
    ToolCallEvidenceItemDTO,
)

_SUITE_INSTANCE: ConclusionEvidenceSuite | None = None


def get_conclusion_evidence_suite() -> ConclusionEvidenceSuite:
    """Retrieve or initialize singleton ConclusionEvidenceSuite."""
    global _SUITE_INSTANCE
    if _SUITE_INSTANCE is None:
        _SUITE_INSTANCE = ConclusionEvidenceSuite()
    return _SUITE_INSTANCE


def reset_conclusion_evidence_suite() -> None:
    """Reset singleton instance for testing isolation."""
    global _SUITE_INSTANCE
    _SUITE_INSTANCE = None


def _to_conclusion_dto(c: AttributedConclusion) -> AttributedConclusionDTO:
    return AttributedConclusionDTO(
        conclusion_id=c.conclusion_id,
        peer_id=c.peer_id,
        content=c.content,
        level=c.level.value if hasattr(c.level, "value") else str(c.level),
        source_ids=list(c.source_ids),
        times_derived=c.times_derived,
        evidence_message_ids=list(c.evidence_message_ids),
        scope_tag=c.scope_tag,
        status=c.status,
        created_at=c.created_at,
        metadata=dict(c.metadata),
    )


def _to_bundle_dto(bundle: ChatEvidenceBundle) -> ChatEvidenceBundleDTO:
    return ChatEvidenceBundleDTO(
        conclusions=[_to_conclusion_dto(c) for c in bundle.conclusions],
        messages=[
            MessageEvidenceItemDTO(
                message_id=m.message_id,
                session_id=m.session_id,
                peer_id=m.peer_id,
                content_snippet=m.content_snippet,
                timestamp=m.timestamp,
            )
            for m in bundle.messages
        ],
        tool_calls=[
            ToolCallEvidenceItemDTO(
                tool_name=tc.tool_name,
                tool_input=dict(tc.tool_input),
                tool_output=tc.tool_output,
            )
            for tc in bundle.tool_calls
        ],
        reasoning_trace_id=bundle.reasoning_trace_id,
    )


def execute_create_conclusion(
    req: CreateAttributedConclusionDTO,
) -> AttributedConclusionDTO:
    """Registers an attributed conclusion in the DAG."""
    suite = get_conclusion_evidence_suite()
    try:
        level_enum = AttributionLevel(req.level)
    except ValueError:
        level_enum = AttributionLevel.EXPLICIT

    conclusion = AttributedConclusion(
        conclusion_id=req.conclusion_id,
        peer_id=req.peer_id,
        content=req.content,
        level=level_enum,
        source_ids=tuple(req.source_ids),
        evidence_message_ids=tuple(req.evidence_message_ids),
        scope_tag=req.scope_tag,
        status=req.status,
        metadata=dict(req.metadata),
    )
    result = suite.add_conclusion(conclusion)
    return _to_conclusion_dto(result)


def query_conclusion(conclusion_id: str) -> AttributedConclusionDTO | None:
    """Retrieves a single conclusion by ID."""
    suite = get_conclusion_evidence_suite()
    c = suite.get_conclusion(conclusion_id)
    if c is None:
        return None
    return _to_conclusion_dto(c)


def query_premises(conclusion_id: str, max_depth: int = 5) -> list[AttributedConclusionDTO]:
    """Retrieves upstream premise conclusions."""
    suite = get_conclusion_evidence_suite()
    premises = suite.get_premise_conclusions(conclusion_id, max_depth=max_depth)
    return [_to_conclusion_dto(c) for c in premises]


def query_derivatives(conclusion_id: str, max_depth: int = 5) -> list[AttributedConclusionDTO]:
    """Retrieves downstream derivative conclusions."""
    suite = get_conclusion_evidence_suite()
    derivatives = suite.get_derived_conclusions(conclusion_id, max_depth=max_depth)
    return [_to_conclusion_dto(c) for c in derivatives]


def query_two_way_traversal(conclusion_id: str, max_depth: int = 5) -> DerivationTraversalViewDTO:
    """Retrieves two-way causal traversal view."""
    suite = get_conclusion_evidence_suite()
    view: DerivationTraversalView = suite.traverse_two_way(conclusion_id, max_depth=max_depth)
    return DerivationTraversalViewDTO(
        conclusion_id=view.conclusion_id,
        upstream_premises=[_to_conclusion_dto(c) for c in view.upstream_premises],
        downstream_derivatives=[_to_conclusion_dto(c) for c in view.downstream_derivatives],
        max_depth=view.max_depth,
    )


def execute_chat_with_evidence(
    req: ChatWithEvidenceRequestDTO,
) -> ChatWithEvidenceResponseDTO:
    """Queries conclusions with optional verifiable evidence packaging."""
    suite = get_conclusion_evidence_suite()
    content, bundle = suite.chat_with_evidence(
        query=req.query,
        peer_id=req.peer_id,
        include_evidence=req.include_evidence,
    )
    bundle_dto = _to_bundle_dto(bundle) if bundle is not None else None
    return ChatWithEvidenceResponseDTO(
        content=content,
        evidence=bundle_dto,
    )


def get_evidence_stats() -> ConclusionEvidenceStatsDTO:
    """Computes attribution graph topology statistics."""
    suite = get_conclusion_evidence_suite()
    stats: ConclusionEvidenceStats = suite.get_stats()
    return ConclusionEvidenceStatsDTO(
        total_conclusions=stats.total_conclusions,
        total_explicit=stats.total_explicit,
        total_derived=stats.total_derived,
        total_edges=stats.total_edges,
        max_derivation_depth=stats.max_derivation_depth,
    )
