"""Graph Memory Service for Reorganization and Lineage Traceability.

[POS]
Business service layer wrapping harness GraphMemoryReorganizationEngine
and MemoryLineageTracker for entity graph mutation, immutable versioning,
bidirectional lineage tracking, and holistic graph reconciliation.
Strictly typed, zero Any, and imports exclusively from harness memory top-level.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional, Tuple

from myrm_agent_harness.toolkits.memory import (
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

logger = logging.getLogger(__name__)


class GraphMemoryService:
    """Manages memory graph operations, immutable evolution, and reorganization."""

    def __init__(self) -> None:
        self._tracker = MemoryLineageTracker()
        self._detector = MultiRelationalDetector()
        self._engine = GraphMemoryReorganizationEngine(
            tracker=self._tracker,
            detector=self._detector,
        )

    def create_node(
        self,
        subject: str,
        predicate: str,
        object_value: str,
        content: Optional[str] = None,
        confidence: float = 1.0,
        source_session_id: Optional[str] = None,
        evidence_quote: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> MemoryGraphNode:
        """Create a new root entity node in the graph."""
        node_id = f"node_{uuid.uuid4().hex[:12]}"
        lineage_root_id = f"root_{uuid.uuid4().hex[:12]}"
        content_str = (
            content if content is not None else f"{subject} {predicate} {object_value}"
        )
        node = MemoryGraphNode(
            node_id=node_id,
            lineage_root_id=lineage_root_id,
            version=1,
            subject=subject,
            predicate=predicate,
            object_value=object_value,
            content=content_str,
            confidence=confidence,
            status=MemoryNodeStatus.ACTIVE,
            source_session_id=source_session_id,
            evidence_quote=evidence_quote,
            metadata=dict(metadata or {}),
        )
        return self._tracker.register_node(node)

    def get_node(self, node_id: str) -> Optional[MemoryGraphNode]:
        """Fetch a specific node by its unique identifier."""
        return self._tracker.get_node(node_id)

    def list_nodes(
        self,
        subject: Optional[str] = None,
        active_only: bool = False,
    ) -> List[MemoryGraphNode]:
        """List nodes matching optional filtering criteria."""
        if active_only:
            return self._tracker.list_active_nodes(subject=subject)
        nodes = self._tracker.list_all_nodes()
        if subject:
            subj_lower = subject.strip().lower()
            nodes = [n for n in nodes if n.subject.strip().lower() == subj_lower]
        return nodes

    def evolve_node(
        self,
        node_id: str,
        object_value: Optional[str] = None,
        content: Optional[str] = None,
        rationale: str = "Memory evolved with updated preferences or factual supersession.",
        metadata: Optional[Dict[str, str]] = None,
    ) -> Tuple[MemoryGraphNode, MemoryGraphNode, MemoryGraphEdge]:
        """Evolve an existing active node, non-destructively creating a superseding version."""
        target_node = self._tracker.get_node(node_id)
        if not target_node:
            raise KeyError(f"Memory node '{node_id}' not found.")

        new_node_id = f"node_{uuid.uuid4().hex[:12]}"
        new_obj = (
            object_value if object_value is not None else target_node.object_value
        )
        new_content = (
            content
            if content is not None
            else f"{target_node.subject} {target_node.predicate} {new_obj}"
        )
        meta = {**target_node.metadata, **(metadata or {})}

        new_node = MemoryGraphNode(
            node_id=new_node_id,
            lineage_root_id=target_node.lineage_root_id,
            version=target_node.version + 1,
            subject=target_node.subject,
            predicate=target_node.predicate,
            object_value=new_obj,
            content=new_content,
            confidence=target_node.confidence,
            status=MemoryNodeStatus.ACTIVE,
            source_session_id=target_node.source_session_id,
            evidence_quote=target_node.evidence_quote,
            metadata=meta,
        )

        return self._engine.record_evolution(
            superseded_node_id=node_id,
            new_node=new_node,
            rationale=rationale,
        )

    def revert_node(
        self,
        historical_node_id: str,
        rationale: str = "Rollback to historical memory version",
    ) -> Tuple[MemoryGraphNode, MemoryGraphNode]:
        """Revert an entity to a target historical version, establishing non-destructive lineage."""
        new_node_id = f"node_{uuid.uuid4().hex[:12]}"
        return self._tracker.revert_to_version(
            historical_node_id=historical_node_id,
            new_node_id=new_node_id,
            rationale=rationale,
        )

    def get_lineage(self, node_id: str) -> MemoryLineageTrail:
        """Trace the full historical audit trail for an entity node."""
        return self._tracker.trace_trail(node_id)

    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        relation_type: GraphRelationType,
        weight: float = 1.0,
        rationale: str = "",
    ) -> MemoryGraphEdge:
        """Create an explicit directional semantic relationship between nodes."""
        edge_id = f"edge_{uuid.uuid4().hex[:8]}"
        edge = MemoryGraphEdge(
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation_type=relation_type,
            weight=weight,
            rationale=rationale,
        )
        return self._tracker.add_edge(edge)

    def list_edges(
        self,
        source_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
        relation_type: Optional[GraphRelationType] = None,
    ) -> List[MemoryGraphEdge]:
        """List graph edges with optional endpoint/relation filters."""
        edges = self._tracker.list_all_edges()
        if source_node_id:
            edges = [e for e in edges if e.source_node_id == source_node_id]
        if target_node_id:
            edges = [e for e in edges if e.target_node_id == target_node_id]
        if relation_type:
            edges = [e for e in edges if e.relation_type == relation_type]
        return edges

    def reorganize(
        self,
        min_confidence: float = 0.8,
    ) -> ReorganizationReport:
        """Run holistic graph reorganization, clustering and inference."""
        return self._engine.run_reorganization_batch(min_confidence=min_confidence)

    def clear(self) -> None:
        """Reset internal store for isolated testing."""
        self._tracker = MemoryLineageTracker()
        self._detector = MultiRelationalDetector()
        self._engine = GraphMemoryReorganizationEngine(
            tracker=self._tracker,
            detector=self._detector,
        )


_service_instance: Optional[GraphMemoryService] = None


def get_graph_memory_service() -> GraphMemoryService:
    """Retrieve singleton instance of GraphMemoryService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = GraphMemoryService()
    return _service_instance
