"""Service layer managing Graph Memory Reorganization and Lineage Traceability.

[POS]
记忆图谱重组与演化溯源链业务服务层。
承接 Harness 框架层图重组引擎与溯源跟踪器，对外暴露强类型 DTO 业务操作接口。

[INPUT]
- app.schemas.memory_lineage::(各种 DTO)
- myrm_agent_harness.toolkits.memory.graph_reorganization::(引擎与数据结构)

[OUTPUT]
- MemoryLineageService: 记忆图谱重组与谱系追溯服务单例
"""

from __future__ import annotations

import uuid

from myrm_agent_harness.toolkits.memory.graph_reorganization import (
    GraphMemoryReorganizationEngine,
    GraphRelationType,
    MemoryGraphEdge,
    MemoryGraphNode,
    MemoryLineageTracker,
    MemoryLineageTrail,
    MemoryNodeStatus,
    MultiRelationalDetector,
    ReorganizationReport,
)

from app.schemas.memory_lineage import (
    LineageRevertResponse,
    LineageStatsDTO,
    LineageStepDTO,
    MemoryGraphEdgeDTO,
    MemoryGraphNodeDTO,
    MemoryLineageTrailDTO,
    MemoryNodeStatusEnum,
    MemoryTopologyGraphDTO,
    ReorganizationBatchResponse,
)


def _node_to_dto(node: MemoryGraphNode) -> MemoryGraphNodeDTO:
    return MemoryGraphNodeDTO(
        node_id=node.node_id,
        lineage_root_id=node.lineage_root_id,
        version=node.version,
        subject=node.subject,
        predicate=node.predicate,
        object_value=node.object_value,
        content=node.content,
        confidence=node.confidence,
        status=MemoryNodeStatusEnum(node.status.value),
        created_at=node.created_at,
        updated_at=node.updated_at,
        source_session_id=node.source_session_id,
        evidence_quote=node.evidence_quote,
        metadata=dict(node.metadata),
    )


def _edge_to_dto(edge: MemoryGraphEdge) -> MemoryGraphEdgeDTO:
    return MemoryGraphEdgeDTO(
        edge_id=edge.edge_id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        relation_type=edge.relation_type.value,  # type: ignore[arg-type]
        weight=edge.weight,
        rationale=edge.rationale,
        created_at=edge.created_at,
    )


class MemoryLineageService:
    """Service orchestrating graph memory reorganization, lineage inspection, and version rollback."""

    def __init__(self) -> None:
        self._tracker = MemoryLineageTracker()
        self._detector = MultiRelationalDetector()
        self._engine = GraphMemoryReorganizationEngine(self._tracker, self._detector)
        self._seed_initial_data_if_empty()

    def _seed_initial_data_if_empty(self) -> None:
        """Seed representative demo nodes across multiple lineage generations and relations."""
        t1 = "2026-10-01T08:00:00Z"
        t2 = "2026-10-04T10:00:00Z"
        t3 = "2026-10-07T14:00:00Z"

        # 1. Evolution Chain: Coffee preference evolution v1 -> v2
        node_v1 = MemoryGraphNode(
            node_id="mem_pref_coffee_v1",
            lineage_root_id="lineage_pref_beverage",
            version=1,
            subject="User",
            predicate="prefers_morning_drink",
            object_value="Black Americano",
            content="User prefers hot black americano with zero sugar for work mornings.",
            confidence=0.92,
            status=MemoryNodeStatus.SUPERSEDED,
            created_at=t1,
            updated_at=t2,
            source_session_id="sess_onboarding_001",
            evidence_quote="I only drink black americano every morning.",
        )
        self._tracker.register_node(node_v1)

        node_v2 = MemoryGraphNode(
            node_id="mem_pref_coffee_v2",
            lineage_root_id="lineage_pref_beverage",
            version=2,
            subject="User",
            predicate="prefers_morning_drink",
            object_value="Iced Oat Latte",
            content="User switched to iced oat latte due to mild stomach discomfort with black coffee.",
            confidence=0.98,
            status=MemoryNodeStatus.ACTIVE,
            created_at=t2,
            updated_at=t2,
            source_session_id="sess_diet_update_042",
            evidence_quote="Black coffee was causing stomach reflux, so I switched to oat latte.",
        )
        self._tracker.register_node(node_v2)

        edge_sup = MemoryGraphEdge(
            edge_id="edge_sup_coffee_2_1",
            source_node_id=node_v2.node_id,
            target_node_id=node_v1.node_id,
            relation_type=GraphRelationType.SUPERSEDES,
            weight=1.0,
            rationale="Explicit user preference update superseding black americano.",
            created_at=t2,
        )
        self._tracker.add_edge(edge_sup)

        # 2. Generalization Subsumption: Tech stack parent -> child
        node_tech_gen = MemoryGraphNode(
            node_id="mem_stack_python",
            lineage_root_id="lineage_stack_python",
            version=1,
            subject="Tech Stack",
            predicate="language_standard",
            object_value="Python 3.12+",
            content="Project adheres strictly to modern Python type hint conventions.",
            confidence=0.95,
            status=MemoryNodeStatus.ACTIVE,
            created_at=t1,
            updated_at=t1,
            source_session_id="sess_init_arch",
        )
        self._tracker.register_node(node_tech_gen)

        node_tech_spec = MemoryGraphNode(
            node_id="mem_stack_pydantic",
            lineage_root_id="lineage_stack_pydantic",
            version=1,
            subject="Tech Stack Pydantic",
            predicate="schema_validation",
            object_value="Pydantic V2 strict models with zero Any",
            content="All API contracts must use Pydantic V2 frozen models with no Any typing allowed.",
            confidence=0.99,
            status=MemoryNodeStatus.ACTIVE,
            created_at=t3,
            updated_at=t3,
            source_session_id="sess_arch_review",
        )
        self._tracker.register_node(node_tech_spec)

        edge_sub = MemoryGraphEdge(
            edge_id="edge_sub_pydantic_python",
            source_node_id=node_tech_gen.node_id,
            target_node_id=node_tech_spec.node_id,
            relation_type=GraphRelationType.SUBSUMPTION,
            weight=0.91,
            rationale="Pydantic strict typing is a domain subsumption under Python 3.12+ type contracts.",
            created_at=t3,
        )
        self._tracker.add_edge(edge_sub)

    def run_reorganization(self, min_confidence: float = 0.8) -> ReorganizationBatchResponse:
        """Trigger an automated graph reorganization batch scan and relation edge synthesis."""
        report: ReorganizationReport = self._engine.run_reorganization_batch(min_confidence=min_confidence)
        return ReorganizationBatchResponse(
            batch_id=report.batch_id,
            analyzed_nodes_count=report.analyzed_nodes_count,
            created_edges_count=report.created_edges_count,
            superseded_nodes_count=report.superseded_nodes_count,
            deductions_count=report.deductions_count,
            edges=[_edge_to_dto(e) for e in report.edges],
            created_at=report.created_at,
        )

    def trace_lineage(self, node_id: str) -> MemoryLineageTrailDTO:
        """Fetch complete explainable lineage DAG trail for a specified memory node."""
        trail: MemoryLineageTrail = self._tracker.trace_trail(node_id)
        steps_dto = [
            LineageStepDTO(
                step_index=s.step_index,
                node=_node_to_dto(s.node),
                relation_to_target=s.relation_to_target.value if s.relation_to_target else None,  # type: ignore[arg-type]
                rationale=s.rationale,
                timestamp=s.timestamp,
            )
            for s in trail.steps
        ]
        return MemoryLineageTrailDTO(
            target_node=_node_to_dto(trail.target_node),
            lineage_root_id=trail.lineage_root_id,
            ancestor_nodes=[_node_to_dto(n) for n in trail.ancestor_nodes],
            descendant_nodes=[_node_to_dto(n) for n in trail.descendant_nodes],
            steps=steps_dto,
            relation_edges=[_edge_to_dto(e) for e in trail.relation_edges],
            depth=trail.depth,
            is_latest=trail.is_latest,
        )

    def revert_version(self, historical_node_id: str, rationale: str) -> LineageRevertResponse:
        """Rollback an active memory slot to a historical version by creating an evolved successor version."""
        new_node_id = f"mem_rev_{uuid.uuid4().hex[:8]}"
        reverted_node, restored_active_node = self._tracker.revert_to_version(
            historical_node_id=historical_node_id,
            new_node_id=new_node_id,
            rationale=rationale,
        )
        return LineageRevertResponse(
            reverted_node=_node_to_dto(reverted_node),
            restored_active_node=_node_to_dto(restored_active_node),
        )

    def get_topology(self) -> MemoryTopologyGraphDTO:
        """Export all registered nodes and relation edges for visual graph topology rendering."""
        all_nodes = self._tracker.list_all_nodes()
        all_edges = self._tracker.list_all_edges()
        return MemoryTopologyGraphDTO(
            nodes=[_node_to_dto(n) for n in all_nodes],
            edges=[_edge_to_dto(e) for e in all_edges],
        )

    def get_stats(self) -> LineageStatsDTO:
        """Compute aggregate health and lineage complexity metrics."""
        nodes = self._tracker.list_all_nodes()
        edges = self._tracker.list_all_edges()

        active_cnt = sum(1 for n in nodes if n.status == MemoryNodeStatus.ACTIVE)
        superseded_cnt = sum(1 for n in nodes if n.status == MemoryNodeStatus.SUPERSEDED)
        reverted_cnt = sum(1 for n in nodes if n.status == MemoryNodeStatus.REVERTED)
        max_ver = max((n.version for n in nodes), default=1)

        return LineageStatsDTO(
            total_nodes=len(nodes),
            active_nodes=active_cnt,
            superseded_nodes=superseded_cnt,
            reverted_nodes=reverted_cnt,
            total_edges=len(edges),
            max_depth=max_ver,
        )


# Global singleton instance for server process
memory_lineage_service = MemoryLineageService()
