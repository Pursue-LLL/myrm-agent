"""[POS]: app/services/memory/directory_dominance_service.py
[INPUT]: API request payloads for hierarchical directory dominance search and evaluation.
[OUTPUT]: DirectoryDominanceService business facade coordinating harness hierarchical retriever.
"""

from myrm_agent_harness.toolkits.memory import (
    DirectoryDominanceConfig,
    DominanceDecisionKind,
    HierarchicalDirectoryDominanceRetriever,
    HierarchicalNode,
    HierarchyNodeType,
)

from app.schemas.directory_dominance import (
    DominanceDecisionAPI,
    DominanceEvaluationRequest,
    DominanceEvaluationResponse,
    HierarchicalNodePayload,
    HierarchicalRetrievalHitPayload,
    HierarchicalRetrievalStatsPayload,
    HierarchicalRetrieveRequest,
    HierarchicalRetrieveResponse,
    HierarchyNodeTypeAPI,
    SiblingContextItemPayload,
)


class DirectoryDominanceService:
    """Service facade managing hierarchical directory dominance retrieval."""

    def _to_harness_node(self, payload: HierarchicalNodePayload) -> HierarchicalNode:
        """Convert API node payload into Harness HierarchicalNode domain entity."""
        return HierarchicalNode(
            uri=payload.uri,
            node_type=HierarchyNodeType(payload.node_type.value),
            name=payload.name,
            parent_uri=payload.parent_uri,
            children_uris=payload.children_uris,
            abstract=payload.abstract,
            content=payload.content,
            score=payload.score,
        )

    def retrieve(self, request: HierarchicalRetrieveRequest) -> HierarchicalRetrieveResponse:
        """Execute hierarchical dominance retrieval bounded by ratio and convergence rounds."""
        config = DirectoryDominanceConfig(
            dominance_ratio=request.dominance_ratio,
            max_convergence_rounds=request.max_convergence_rounds,
            max_parallel_child_searches=request.max_parallel_child_searches,
            max_siblings_per_hit=request.max_siblings_per_hit,
            include_parent_context=request.include_parent_context,
        )
        retriever = HierarchicalDirectoryDominanceRetriever(config=config)
        harness_nodes = [self._to_harness_node(n) for n in request.nodes]

        raw_result = retriever.retrieve(
            query=request.query,
            nodes=harness_nodes,
            limit=request.limit,
        )

        hits_payload = [
            HierarchicalRetrievalHitPayload(
                uri=hit.uri,
                node_type=HierarchyNodeTypeAPI(hit.node_type.value),
                score=hit.score,
                decision=DominanceDecisionAPI(hit.decision.value),
                abstract=hit.abstract,
                content=hit.content,
                parent_uri=hit.parent_uri,
                parent_summary=hit.parent_summary,
                sibling_contexts=[
                    SiblingContextItemPayload(
                        uri=sib.uri,
                        name=sib.name,
                        abstract=sib.abstract,
                        relation=sib.relation,
                    )
                    for sib in hit.sibling_contexts
                ],
            )
            for hit in raw_result.hits
        ]

        stats_payload = HierarchicalRetrievalStatsPayload(
            convergence_rounds=raw_result.stats.convergence_rounds,
            nodes_evaluated=raw_result.stats.nodes_evaluated,
            dominant_directories_count=raw_result.stats.dominant_directories_count,
            leaf_hits_count=raw_result.stats.leaf_hits_count,
            total_siblings_bundled=raw_result.stats.total_siblings_bundled,
        )

        return HierarchicalRetrieveResponse(
            query=raw_result.query,
            hits=hits_payload,
            stats=stats_payload,
        )

    def evaluate_dominance(self, request: DominanceEvaluationRequest) -> DominanceEvaluationResponse:
        """Evaluate directory dominance ratio against its immediate children."""
        config = DirectoryDominanceConfig(dominance_ratio=request.dominance_ratio)
        retriever = HierarchicalDirectoryDominanceRetriever(config=config)

        dir_node = self._to_harness_node(request.dir_node)
        children = [self._to_harness_node(c) for c in request.children_nodes]

        decision: DominanceDecisionKind = retriever.evaluate_dominance(dir_node, children)
        max_child_score = max((c.score for c in children), default=0.0)
        required_threshold = max_child_score * request.dominance_ratio

        return DominanceEvaluationResponse(
            dir_uri=dir_node.uri,
            dir_score=dir_node.score,
            max_child_score=max_child_score,
            dominance_ratio=request.dominance_ratio,
            required_threshold=required_threshold,
            decision=DominanceDecisionAPI(decision.value),
        )


_instance: DirectoryDominanceService | None = None


def get_directory_dominance_service() -> DirectoryDominanceService:
    """Singleton provider for DirectoryDominanceService."""
    global _instance
    if _instance is None:
        _instance = DirectoryDominanceService()
    return _instance
