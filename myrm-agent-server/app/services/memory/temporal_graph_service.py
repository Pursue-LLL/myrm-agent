"""[POS]: app/services/memory/temporal_graph_service.py
[INPUT]: Harness temporal_graph store, decay scorer, reconciler, and server DTO schemas.
[OUTPUT]: TemporalGraphService orchestrating entity nodes, temporal fact edge conflict resolution, and decay scoring.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    SqliteTemporalGraphStore,
    TemporalDecayScorer,
    TemporalEntityNode,
    TemporalFactConflictReconciler,
    TemporalFactEdge,
)

from app.schemas.temporal_graph import (
    FactConflictResolutionResultDTO,
    SaveEntityNodeRequestDTO,
    SaveFactEdgeRequestDTO,
    TemporalEntityNodeDTO,
    TemporalFactEdgeDTO,
    TemporalFactHitDTO,
    TemporalGraphStatsDTO,
)


class TemporalGraphService:
    """Business service orchestrating temporal knowledge graph evolution and fact reconciliation."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        half_life_days: float = 30.0,
    ) -> None:
        self._store = SqliteTemporalGraphStore(db_path=db_path)
        self._scorer = TemporalDecayScorer(half_life_days=half_life_days)
        self._reconciler = TemporalFactConflictReconciler()

    def save_node(self, request: SaveEntityNodeRequestDTO) -> TemporalEntityNodeDTO:
        """Saves or updates a temporal entity node."""
        node_id = request.node_id or f"ent_{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        existing = self._store.get_node(node_id)
        created_at = existing.created_at if existing else now

        node = TemporalEntityNode(
            node_id=node_id,
            name=request.name.strip(),
            entity_type=request.entity_type.strip(),
            attributes=request.attributes,
            created_at=created_at,
            updated_at=now,
        )
        saved = self._store.save_node(node)
        return self._node_to_dto(saved)

    def get_node(self, node_id: str) -> TemporalEntityNodeDTO | None:
        """Retrieves an entity node by ID."""
        node = self._store.get_node(node_id)
        return self._node_to_dto(node) if node else None

    def list_nodes(self, entity_type: str | None = None, limit: int = 100) -> list[TemporalEntityNodeDTO]:
        """Lists entity nodes optionally filtered by type."""
        nodes = self._store.list_nodes(entity_type=entity_type, limit=limit)
        return [self._node_to_dto(n) for n in nodes]

    def delete_node(self, node_id: str) -> bool:
        """Deletes an entity node and its associated relationship edges."""
        return self._store.delete_node(node_id)

    def save_fact_edge_with_reconciliation(
        self,
        request: SaveFactEdgeRequestDTO,
    ) -> FactConflictResolutionResultDTO:
        """Inserts a new fact edge, detecting mutual exclusivity conflicts and superseding legacy facts."""
        edge_id = request.edge_id or f"edge_{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)

        edge = TemporalFactEdge(
            edge_id=edge_id,
            source_id=request.source_id.strip(),
            target_id=request.target_id.strip(),
            predicate=request.predicate.strip().lower(),
            valid_from=now,
            confidence_score=request.confidence_score,
            created_at=now,
        )

        outcome = self._reconciler.resolve_and_insert(self._store, edge)

        return FactConflictResolutionResultDTO(
            new_edge=self._edge_to_dto(outcome.new_edge),
            superseded_edges=[self._edge_to_dto(e) for e in outcome.superseded_edges],
            is_conflict_detected=outcome.is_conflict_detected,
            conflict_reason=outcome.conflict_reason,
        )

    def get_edge(self, edge_id: str) -> TemporalFactEdgeDTO | None:
        """Retrieves a relationship edge by ID."""
        edge = self._store.get_edge(edge_id)
        return self._edge_to_dto(edge) if edge else None

    def list_edges(
        self,
        predicate: str | None = None,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[TemporalFactEdgeDTO]:
        """Lists stored relationship edges."""
        edges = self._store.list_edges(predicate=predicate, active_only=active_only, limit=limit)
        return [self._edge_to_dto(e) for e in edges]

    def get_lineage(self, edge_id: str) -> list[TemporalFactEdgeDTO]:
        """Traces the backward historical lineage of superseded edges leading to the given edge."""
        lineage = self._reconciler.get_supersession_lineage(self._store, edge_id)
        return [self._edge_to_dto(e) for e in lineage]

    def query_temporal_facts(
        self,
        source_id: str | None = None,
        predicate: str | None = None,
        active_only: bool = True,
        limit: int = 50,
    ) -> list[TemporalFactHitDTO]:
        """Queries fact edges with dynamic half-life decay scoring."""
        if source_id and predicate:
            edges = self._store.get_edges_by_source_predicate(
                source_id=source_id,
                predicate=predicate,
                active_only=active_only,
            )
        elif source_id:
            edges = self._store.get_out_edges(source_id=source_id, active_only=active_only)
        else:
            edges = self._store.list_edges(predicate=predicate, active_only=active_only, limit=limit)

        now = datetime.now(UTC)
        hits: list[TemporalFactHitDTO] = []

        for edge in edges:
            decayed_score, status = self._scorer.calculate_score(edge, as_of=now)
            source_node = self._store.get_node(edge.source_id) or TemporalEntityNode(
                node_id=edge.source_id, name=edge.source_id, entity_type="unknown"
            )
            target_node = self._store.get_node(edge.target_id) or TemporalEntityNode(
                node_id=edge.target_id, name=edge.target_id, entity_type="unknown"
            )

            hits.append(
                TemporalFactHitDTO(
                    edge=self._edge_to_dto(edge),
                    source_node=self._node_to_dto(source_node),
                    target_node=self._node_to_dto(target_node),
                    decayed_score=decayed_score,
                    effective_status=status,
                )
            )

        # Sort descending by calculated decay score
        hits.sort(key=lambda h: h.decayed_score, reverse=True)
        return hits[:limit]

    def get_stats(self) -> TemporalGraphStatsDTO:
        """Computes summary metrics for the temporal knowledge graph."""
        nodes = self._store.list_nodes(limit=1000)
        active_edges = self._store.list_edges(active_only=True, limit=1000)
        all_edges = self._store.list_edges(active_only=False, limit=1000)
        superseded_count = sum(1 for e in all_edges if e.is_superseded)

        now = datetime.now(UTC)
        if active_edges:
            scores = [self._scorer.calculate_score(e, as_of=now)[0] for e in active_edges]
            avg_score = round(sum(scores) / len(scores), 3)
        else:
            avg_score = 1.0

        return TemporalGraphStatsDTO(
            total_nodes_count=len(nodes),
            active_edges_count=len(active_edges),
            superseded_edges_count=superseded_count,
            average_decayed_score=avg_score,
        )

    @staticmethod
    def _node_to_dto(node: TemporalEntityNode) -> TemporalEntityNodeDTO:
        return TemporalEntityNodeDTO(
            node_id=node.node_id,
            name=node.name,
            entity_type=node.entity_type,
            attributes=node.attributes,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )

    @staticmethod
    def _edge_to_dto(edge: TemporalFactEdge) -> TemporalFactEdgeDTO:
        return TemporalFactEdgeDTO(
            edge_id=edge.edge_id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            predicate=edge.predicate,
            valid_from=edge.valid_from,
            valid_until=edge.valid_until,
            is_superseded=edge.is_superseded,
            superseded_by=edge.superseded_by,
            confidence_score=edge.confidence_score,
            access_count=edge.access_count,
            last_accessed_at=edge.last_accessed_at,
            created_at=edge.created_at,
        )


_temporal_graph_service_instance: TemporalGraphService | None = None


def get_temporal_graph_service() -> TemporalGraphService:
    """Dependency injector singleton for TemporalGraphService."""
    global _temporal_graph_service_instance
    if _temporal_graph_service_instance is None:
        _temporal_graph_service_instance = TemporalGraphService()
    return _temporal_graph_service_instance
