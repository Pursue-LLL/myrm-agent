"""Service layer for Diamond Topology Orchestrator and Blinded Adversarial Auditor."""

from typing import Dict, List, Optional, Tuple

from myrm_agent_harness.agent.sub_agents.diamond_graph import (
    BlindedAdversarialAuditor,
    CensusStatus,
    DiamondGraphOrchestrator,
    DiamondNode,
    RealityAnchorSpec,
    RealityAnchorType,
)

from app.schemas.diamond_graph import (
    AdversarialReviewItemDTO,
    AdversarialVerdictDTO,
    AuditorPerspectiveEnum,
    CensusStatusDTO,
    DiamondNodeDTO,
    DiamondStageEnum,
    RealityAnchorSpecDTO,
    RealityAnchorTypeEnum,
)


class DiamondGraphService:
    """Session-isolated service managing Diamond DAG orchestration and Blinded Adversarial Auditing."""

    def __init__(self) -> None:
        self._orchestrators: Dict[str, DiamondGraphOrchestrator] = {}
        self._auditors: Dict[str, BlindedAdversarialAuditor] = {}

    def _get_bundle(self, chat_id: str) -> Tuple[DiamondGraphOrchestrator, BlindedAdversarialAuditor]:
        if chat_id not in self._orchestrators:
            self._orchestrators[chat_id] = DiamondGraphOrchestrator()
            self._auditors[chat_id] = BlindedAdversarialAuditor(pass_vote_ratio=0.67)
        return self._orchestrators[chat_id], self._auditors[chat_id]

    def _to_node_dto(self, node: DiamondNode, mask_cot: bool = False) -> DiamondNodeDTO:
        cot = None if mask_cot else node.cot_reasoning_internal
        return DiamondNodeDTO(
            node_id=node.node_id,
            title=node.title,
            stage=DiamondStageEnum(node.stage.value),
            depends_on=list(node.depends_on),
            payload=dict(node.payload),
            output_artifact=node.output_artifact,
            cot_reasoning_internal=cot,
            is_pruned=node.is_pruned,
            status=node.status,
            created_at=node.created_at,
        )

    def _to_census_dto(self, census: CensusStatus) -> CensusStatusDTO:
        return CensusStatusDTO(
            dispatched_count=census.dispatched_count,
            received_count=census.received_count,
            missing_nodes=list(census.missing_nodes),
            is_healthy=census.is_healthy,
            retried_nodes=list(census.retried_nodes),
        )

    def create_pipeline(
        self,
        chat_id: str,
        goal: str,
        fan_out_specs: List[Dict[str, str]],
    ) -> List[DiamondNodeDTO]:
        orch, _ = self._get_bundle(chat_id)
        fan_nodes, reduce_node, synth_node = orch.create_diamond_pipeline(goal, fan_out_specs)
        all_nodes = [*fan_nodes, reduce_node, synth_node]
        return [self._to_node_dto(n) for n in all_nodes]

    def prune_false_dependencies(self, chat_id: str) -> Tuple[List[List[str]], int]:
        orch, _ = self._get_bundle(chat_id)
        pruned = orch.prune_false_dependencies()
        pruned_pairs = [[edge[0], edge[1]] for edge in pruned]
        remaining_count = len(orch.get_nodes())
        return pruned_pairs, remaining_count

    def dispatch_fan_out(self, chat_id: str) -> CensusStatusDTO:
        orch, _ = self._get_bundle(chat_id)
        census = orch.dispatch_fan_out()
        return self._to_census_dto(census)

    def record_node_completion(
        self,
        chat_id: str,
        node_id: str,
        output_artifact: str,
        cot_reasoning_internal: Optional[str] = None,
        success: bool = True,
    ) -> DiamondNodeDTO:
        orch, _ = self._get_bundle(chat_id)
        node = orch.record_node_completion(
            node_id=node_id,
            output_artifact=output_artifact,
            cot_reasoning_internal=cot_reasoning_internal,
            success=success,
        )
        return self._to_node_dto(node)

    def check_census(self, chat_id: str) -> CensusStatusDTO:
        orch, _ = self._get_bundle(chat_id)
        census = orch.check_census()
        return self._to_census_dto(census)

    def retry_dead_nodes(self, chat_id: str) -> List[str]:
        orch, _ = self._get_bundle(chat_id)
        return orch.retry_dead_nodes()

    def execute_deterministic_reduce(self, chat_id: str) -> str:
        orch, _ = self._get_bundle(chat_id)
        return orch.execute_deterministic_reduce()

    def execute_synthesis(
        self, chat_id: str, summary_prefix: str = "Consolidated Architecture Synthesis:\n"
    ) -> str:
        orch, _ = self._get_bundle(chat_id)
        return orch.execute_synthesis(summary_prefix=summary_prefix)

    def get_nodes(self, chat_id: str, mask_cot: bool = False) -> List[DiamondNodeDTO]:
        orch, _ = self._get_bundle(chat_id)
        return [self._to_node_dto(n, mask_cot=mask_cot) for n in orch.get_nodes()]

    def audit_delivery(
        self,
        chat_id: str,
        artifact: str,
        reality_anchors: List[RealityAnchorSpecDTO],
        pass_vote_ratio: float = 0.67,
    ) -> AdversarialVerdictDTO:
        _, auditor = self._get_bundle(chat_id)
        auditor.pass_vote_ratio = pass_vote_ratio

        anchor_specs = [
            RealityAnchorSpec(
                anchor_type=RealityAnchorType(a.anchor_type.value),
                target_id=a.target_id,
                expected_value=a.expected_value,
                actual_value=a.actual_value,
            )
            for a in reality_anchors
        ]

        verdict = auditor.evaluate_delivery(artifact=artifact, reality_anchors=anchor_specs)

        reviews_dto = [
            AdversarialReviewItemDTO(
                perspective=AuditorPerspectiveEnum(r.perspective.value),
                auditor_id=r.auditor_id,
                passed=r.passed,
                score=r.score,
                critique=r.critique,
                isolated_context_verified=r.isolated_context_verified,
                timestamp=r.timestamp,
            )
            for r in verdict.reviews
        ]

        anchors_dto = [
            RealityAnchorSpecDTO(
                anchor_type=RealityAnchorTypeEnum(ac.anchor_type.value),
                target_id=ac.target_id,
                expected_value=ac.expected_value,
                actual_value=ac.actual_value,
                verified=ac.verified,
            )
            for ac in verdict.anchor_checks
        ]

        return AdversarialVerdictDTO(
            passed=verdict.passed,
            total_reviews=verdict.total_reviews,
            pass_count=verdict.pass_count,
            reviews=reviews_dto,
            anchor_checks=anchors_dto,
            consensus_summary=verdict.consensus_summary,
            timestamp=verdict.timestamp,
        )

    def reset_session(self, chat_id: str) -> None:
        self._orchestrators.pop(chat_id, None)
        self._auditors.pop(chat_id, None)


_singleton_diamond_graph_service = DiamondGraphService()


def get_diamond_graph_service() -> DiamondGraphService:
    """Return the global singleton instance of DiamondGraphService."""
    return _singleton_diamond_graph_service
