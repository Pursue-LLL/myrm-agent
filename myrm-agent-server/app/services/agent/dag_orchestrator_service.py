"""Service layer for DAG Visual Orchestrator with Cold Resume and Bidirectional Feedback."""

from typing import Dict, Optional

from myrm_agent_harness.agent.sub_agents.dag_orchestrator import (
    DagColdResumeEngine,
    DagDependencyPlanner,
    DagNode,
    DagNodeStatus,
    DagPlanResult,
)

from app.schemas.dag_orchestrator import (
    DagColdResumeResponse,
    DagNodeDTO,
    DagNodeStatusEnum,
    DagPlanResponse,
    DagRejectLoopbackResponse,
    DagRoleEnum,
    DagStatusResponse,
)


class DagNotFoundError(KeyError):
    """Raised when the specified DAG ID is not found in active workspaces."""


class DagOrchestratorService:
    """Coordinates multi-agent DAG planning, state persistence, cold resume, and feedback loopback."""

    def __init__(self) -> None:
        self.planner = DagDependencyPlanner()
        self.engine = DagColdResumeEngine(planner=self.planner)
        self._dags: Dict[str, Dict[str, DagNode]] = {}
        self._goals: Dict[str, str] = {}

    def plan_dag(self, goal: str, dag_id: Optional[str] = None) -> DagPlanResponse:
        """Decompose a natural language goal into a validated DAG."""
        plan_result: DagPlanResult = self.planner.plan_team_dag(goal=goal, dag_id=dag_id or "")
        active_id = plan_result.dag_id
        self._dags[active_id] = plan_result.nodes
        self._goals[active_id] = goal

        # Save initial checkpoint
        self.engine.save_checkpoint(active_id, plan_result.nodes)

        return DagPlanResponse(
            dag_id=active_id,
            goal=goal,
            nodes=self._to_nodes_dto(plan_result.nodes),
            topological_order=plan_result.topological_order,
            ready_node_ids=plan_result.ready_node_ids,
        )

    def get_dag(self, dag_id: str) -> DagStatusResponse:
        """Fetch current DAG state, ready nodes, and completion status."""
        nodes = self._get_nodes(dag_id)
        ready_ids = self.planner.get_ready_nodes(nodes)
        is_completed = all(n.status == DagNodeStatus.COMPLETED for n in nodes.values())

        return DagStatusResponse(
            dag_id=dag_id,
            goal=self._goals.get(dag_id, ""),
            nodes=self._to_nodes_dto(nodes),
            ready_node_ids=ready_ids,
            is_completed=is_completed,
        )

    def execute_step(self, dag_id: str, node_id: str) -> DagStatusResponse:
        """Advance a single ready node to completion and update checkpoint."""
        nodes = self._get_nodes(dag_id)
        # Execute node
        self.engine.execute_node_step(nodes, node_id)
        # Persist checkpoint after successful execution
        self.engine.save_checkpoint(dag_id, nodes)

        ready_ids = self.planner.get_ready_nodes(nodes)
        is_completed = all(n.status == DagNodeStatus.COMPLETED for n in nodes.values())

        return DagStatusResponse(
            dag_id=dag_id,
            goal=self._goals.get(dag_id, ""),
            nodes=self._to_nodes_dto(nodes),
            ready_node_ids=ready_ids,
            is_completed=is_completed,
        )

    def cold_resume(self, dag_id: str) -> DagColdResumeResponse:
        """Cold-resume execution state from last valid checkpoint without repeating work."""
        restored_nodes, ready_ids = self.engine.cold_resume(dag_id)
        self._dags[dag_id] = restored_nodes

        completed_count = sum(
            1 for n in restored_nodes.values() if n.status == DagNodeStatus.COMPLETED
        )

        return DagColdResumeResponse(
            dag_id=dag_id,
            nodes=self._to_nodes_dto(restored_nodes),
            ready_node_ids=ready_ids,
            completed_count=completed_count,
        )

    def reject_loopback(
        self, dag_id: str, target_node_id: str, feedback: str
    ) -> DagRejectLoopbackResponse:
        """Trigger downstream cascade reject loopback with structured feedback."""
        nodes = self._get_nodes(dag_id)
        affected = self.engine.reject_and_loopback(nodes, target_node_id, feedback)

        # Persist updated checkpoint
        self.engine.save_checkpoint(dag_id, nodes)
        ready_ids = self.planner.get_ready_nodes(nodes)

        return DagRejectLoopbackResponse(
            target_node_id=target_node_id,
            affected_node_ids=sorted(affected),
            nodes=self._to_nodes_dto(nodes),
            next_ready_node_ids=ready_ids,
        )

    def reset(self) -> None:
        """Reset service state for test teardown."""
        self._dags.clear()
        self._goals.clear()
        self.engine.clear()

    def _get_nodes(self, dag_id: str) -> Dict[str, DagNode]:
        nodes = self._dags.get(dag_id)
        if not nodes:
            raise DagNotFoundError(f"DAG '{dag_id}' not found in active service.")
        return nodes

    def _to_nodes_dto(self, nodes: Dict[str, DagNode]) -> Dict[str, DagNodeDTO]:
        return {
            nid: DagNodeDTO(
                node_id=n.node_id,
                role=DagRoleEnum(n.role.value),
                title=n.title,
                instruction=n.instruction,
                depends_on=list(n.depends_on),
                status=DagNodeStatusEnum(n.status.value),
                output_artifact=n.output_artifact,
                rejection_feedback=n.rejection_feedback,
                execution_time_ms=n.execution_time_ms,
            )
            for nid, n in nodes.items()
        }


_GLOBAL_SERVICE: Optional[DagOrchestratorService] = None


def get_dag_orchestrator_service() -> DagOrchestratorService:
    """Retrieve singleton instance of DagOrchestratorService."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = DagOrchestratorService()
    return _GLOBAL_SERVICE
