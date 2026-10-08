"""Business domain provider for Conclusion Attribution and Chat Evidence (Item 141).

Wraps the pure execution harness ConclusionAttributionSuite, converts between domain
entities and API schemas, and maintains single-process state.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.conclusion_attribution import (
    AttributedConclusion,
    AttributionLevel,
    AttributionMetrics,
    ChatEvidence,
    ConclusionAttributionSuite,
    GraphTraversalNode,
    RippleImpactReport,
)

from app.schemas.conclusion_attribution import (
    AttributedConclusionDTO,
    AttributionMetricsResponse,
    ChatEvidenceDTO,
    GraphTraversalNodeDTO,
    MessageReferenceDTO,
    RippleImpactResponse,
    ToolCallRecordDTO,
)


def _to_dto(c: AttributedConclusion) -> AttributedConclusionDTO:
    return AttributedConclusionDTO(
        id=c.id,
        peer_id=c.peer_id,
        content=c.content,
        level=str(c.level.value),
        source_ids=list(c.source_ids),
        times_derived=c.times_derived,
        session_id=c.session_id,
        confidence=c.confidence,
        created_at=c.created_at,
        updated_at=c.updated_at,
        metadata=dict(c.metadata),
    )


def _to_node_dto(n: GraphTraversalNode) -> GraphTraversalNodeDTO:
    return GraphTraversalNodeDTO(
        conclusion=_to_dto(n.conclusion),
        depth=n.depth,
        direct_parent_ids=list(n.direct_parent_ids),
        direct_child_ids=list(n.direct_child_ids),
    )


def _to_evidence_dto(e: ChatEvidence) -> ChatEvidenceDTO:
    return ChatEvidenceDTO(
        conclusions=[_to_dto(c) for c in e.conclusions],
        messages=[
            MessageReferenceDTO(
                message_id=m.message_id,
                session_id=m.session_id,
                role=m.role,
                snippet=m.snippet,
                timestamp=m.timestamp,
            )
            for m in e.messages
        ],
        tool_calls=[
            ToolCallRecordDTO(
                tool_name=t.tool_name,
                tool_input=dict(t.tool_input),
                tool_output_snippet=t.tool_output_snippet,
            )
            for t in e.tool_calls
        ],
        reasoning_trace_id=e.reasoning_trace_id,
    )


class ConclusionAttributionProvider:
    """Singleton domain provider bridging API requests to harness suite."""

    _instance: ConclusionAttributionProvider | None = None

    def __init__(self) -> None:
        self.suite = ConclusionAttributionSuite()

    @classmethod
    def get_instance(cls) -> ConclusionAttributionProvider:
        if cls._instance is None:
            cls._instance = ConclusionAttributionProvider()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset instance for clean test suites."""
        cls._instance = None

    def create_conclusion(
        self,
        peer_id: str,
        content: str,
        level: str = "explicit",
        source_ids: list[str] | None = None,
        session_id: str | None = None,
        confidence: float = 1.0,
        metadata: dict[str, str] | None = None,
    ) -> AttributedConclusionDTO:
        parsed_level = AttributionLevel(level)
        item = self.suite.create_conclusion(
            peer_id=peer_id,
            content=content,
            level=parsed_level,
            source_ids=source_ids,
            session_id=session_id,
            confidence=confidence,
            metadata=metadata,
        )
        return _to_dto(item)

    def list_conclusions(
        self,
        peer_id: str | None = None,
        session_id: str | None = None,
        level: str | None = None,
        reverse: bool = False,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[AttributedConclusionDTO], int]:
        parsed_level = AttributionLevel(level) if level else None
        items, total = self.suite.list_conclusions(
            peer_id=peer_id,
            session_id=session_id,
            level=parsed_level,
            reverse=reverse,
            page=page,
            size=size,
        )
        return [_to_dto(c) for c in items], total

    def query_conclusions(
        self,
        query: str,
        peer_id: str | None = None,
        level: str | None = None,
        top_k: int = 10,
    ) -> list[AttributedConclusionDTO]:
        parsed_level = AttributionLevel(level) if level else None
        items = self.suite.query_conclusions(
            query=query,
            peer_id=peer_id,
            level=parsed_level,
            top_k=top_k,
        )
        return [_to_dto(c) for c in items]

    def walk_downward(self, conclusion_id: str, max_depth: int = 15) -> list[GraphTraversalNodeDTO]:
        nodes = self.suite.walk_downward(conclusion_id, max_depth)
        return [_to_node_dto(n) for n in nodes]

    def walk_upward(self, premise_id: str, max_depth: int = 15) -> list[GraphTraversalNodeDTO]:
        nodes = self.suite.walk_upward(premise_id, max_depth)
        return [_to_node_dto(n) for n in nodes]

    def get_ripple_impact(self, conclusion_id: str) -> RippleImpactResponse:
        report: RippleImpactReport = self.suite.get_ripple_impact(conclusion_id)
        return RippleImpactResponse(
            target_conclusion_id=report.target_conclusion_id,
            impacted_conclusion_ids=report.impacted_conclusion_ids,
            depth_reached=report.depth_reached,
            severity=report.severity,
            explanation=report.explanation,
        )

    def delete_conclusion(self, conclusion_id: str, cascade: bool = False) -> list[str]:
        return self.suite.delete_conclusion(conclusion_id, cascade=cascade)

    def chat_with_evidence(
        self,
        query: str,
        peer_id: str,
        session_id: str | None = None,
        include_evidence: bool = True,
    ) -> tuple[str, ChatEvidenceDTO | None]:
        # Formulate contextual response
        matched = self.query_conclusions(query, peer_id=peer_id, top_k=3)
        if matched:
            top_facts = " ".join([f"[{c.level}] {c.content}" for c in matched[:2]])
            reply = f"Based on verified memory: {top_facts}"
        else:
            reply = f"I noted your query '{query}'."

        evidence_dto: ChatEvidenceDTO | None = None
        if include_evidence:
            pkg: ChatEvidence = self.suite.create_evidence_package(
                query=query,
                peer_id=peer_id,
                session_id=session_id,
                top_k=3,
            )
            evidence_dto = _to_evidence_dto(pkg)

        return reply, evidence_dto

    def get_metrics(self, peer_id: str | None = None) -> AttributionMetricsResponse:
        m: AttributionMetrics = self.suite.get_metrics(peer_id=peer_id)
        return AttributionMetricsResponse(
            total_conclusions=m.total_conclusions,
            explicit_count=m.explicit_count,
            deductive_count=m.deductive_count,
            inductive_count=m.inductive_count,
            contradiction_count=m.contradiction_count,
            max_derivation_depth=m.max_derivation_depth,
            average_times_derived=m.average_times_derived,
        )
