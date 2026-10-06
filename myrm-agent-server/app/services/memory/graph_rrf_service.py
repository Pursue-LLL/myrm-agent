"""
[POS] app/services/memory/graph_rrf_service.py
[INPUT] app/schemas/graph_rrf.py, myrm_agent_harness.toolkits.memory.graph_rrf
[OUTPUT] GraphRRFMemoryService, get_graph_rrf_service
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory.graph_rrf import (
    DualChannelRRFRetriever,
    EntityNode,
    RelationEdge,
    RRFConfig,
    SQLiteGraphMemoryStore,
    VectorHit,
)

from app.schemas.graph_rrf import (
    DualChannelSearchRequest,
    DualChannelSearchResponse,
    EntityNodeCreateRequest,
    EntityNodeResponse,
    FusedMemoryHitResponse,
    GraphTraverseRequest,
    GraphTraverseResponse,
    MemoryAssociationRequest,
    RelationEdgeCreateRequest,
    RelationEdgeResponse,
)


class GraphRRFMemoryService:
    """Service facade managing knowledge graph memory store and dual-channel RRF retrieval."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.store = SQLiteGraphMemoryStore(db_path=db_path)

    def add_entity_node(self, req: EntityNodeCreateRequest) -> EntityNodeResponse:
        """Create or update an entity node."""
        node = EntityNode(
            id=req.id,
            name=req.name,
            entity_type=req.entity_type,
            properties=dict(req.properties),
        )
        self.store.add_node(node)
        persisted = self.store.get_node(req.id)
        if not persisted:
            persisted = node
        return EntityNodeResponse(
            id=persisted.id,
            name=persisted.name,
            entity_type=persisted.entity_type,
            properties=persisted.properties,
            created_at=persisted.created_at,
        )

    def get_entity_node(self, node_id: str) -> EntityNodeResponse | None:
        """Retrieve an entity node by ID."""
        persisted = self.store.get_node(node_id)
        if not persisted:
            return None
        return EntityNodeResponse(
            id=persisted.id,
            name=persisted.name,
            entity_type=persisted.entity_type,
            properties=persisted.properties,
            created_at=persisted.created_at,
        )

    def add_relation_edge(
        self, req: RelationEdgeCreateRequest
    ) -> RelationEdgeResponse:
        """Create or update a relationship edge."""
        edge = RelationEdge(
            id=req.id,
            source_id=req.source_id,
            target_id=req.target_id,
            relation_type=req.relation_type,
            weight=req.weight,
            properties=dict(req.properties),
        )
        self.store.add_edge(edge)
        return RelationEdgeResponse(
            id=edge.id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation_type=edge.relation_type,
            weight=edge.weight,
            properties=edge.properties,
            created_at=edge.created_at,
        )

    def associate_memory(self, req: MemoryAssociationRequest) -> None:
        """Link a memory unit with an entity node."""
        self.store.associate_memory(
            memory_id=req.memory_id,
            entity_id=req.entity_id,
            content=req.content,
        )

    def traverse_graph(self, req: GraphTraverseRequest) -> GraphTraverseResponse:
        """Execute BFS traversal from seed entities."""
        result = self.store.traverse(
            seed_entity_ids=req.seed_entity_ids,
            max_hops=req.max_hops,
            allowed_relations=req.allowed_relations,
        )
        nodes_resp = [
            EntityNodeResponse(
                id=n.id,
                name=n.name,
                entity_type=n.entity_type,
                properties=n.properties,
                created_at=n.created_at,
            )
            for n in result.nodes
        ]
        edges_resp = [
            RelationEdgeResponse(
                id=e.id,
                source_id=e.source_id,
                target_id=e.target_id,
                relation_type=e.relation_type,
                weight=e.weight,
                properties=e.properties,
                created_at=e.created_at,
            )
            for e in result.edges
        ]
        paths_resp = [
            {
                "source_id": p.source_id,
                "target_id": p.target_id,
                "relation_type": p.relation_type,
                "depth": p.depth,
            }
            for p in result.paths
        ]
        return GraphTraverseResponse(
            nodes=nodes_resp,
            edges=edges_resp,
            paths=paths_resp,
            associated_memory_ids=result.associated_memory_ids,
        )

    def search_dual_channel(
        self, req: DualChannelSearchRequest
    ) -> DualChannelSearchResponse:
        """Execute dual-channel search and return fused memory hits."""
        # Wrap vector candidates if provided
        vector_hits: list[VectorHit] = []
        if req.vector_candidates:
            vector_hits = [
                VectorHit(
                    memory_id=c.memory_id,
                    content=c.content,
                    score=c.score,
                    rank=c.rank,
                )
                for c in req.vector_candidates
            ]

        def vector_search_fn(_query: str, _top_k: int) -> list[VectorHit]:
            return vector_hits

        config = RRFConfig(
            k=req.k,
            vector_weight=req.vector_weight,
            graph_weight=req.graph_weight,
            max_graph_hops=req.max_graph_hops,
            top_k=req.top_k,
        )
        retriever = DualChannelRRFRetriever(
            graph_store=self.store,
            vector_search_fn=vector_search_fn if req.vector_candidates is not None else None,
            config=config,
        )

        fused_hits = retriever.search(
            query=req.query,
            seed_entity_ids=req.seed_entity_ids,
            seed_entity_names=req.seed_entity_names,
            top_k=req.top_k,
        )

        results = [
            FusedMemoryHitResponse(
                memory_id=h.memory_id,
                content=h.content,
                fused_score=h.fused_score,
                vector_rank=h.vector_rank,
                graph_rank=h.graph_rank,
                hit_sources=h.hit_sources,
                explanation=h.explanation,
            )
            for h in fused_hits
        ]
        return DualChannelSearchResponse(
            results=results,
            total_hits=len(results),
            query=req.query,
        )


_default_service: GraphRRFMemoryService | None = None


def get_graph_rrf_service() -> GraphRRFMemoryService:
    """Return default singleton instance for GraphRRFMemoryService."""
    global _default_service
    if _default_service is None:
        _default_service = GraphRRFMemoryService()
    return _default_service
