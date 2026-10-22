from typing import ClassVar

from myrm_agent_harness.agent.sub_agents.graph_triage import (
    BudgetCapConfig,
    ElasticConcurrencyReducer,
    GraphApplicabilityTriageGate,
    PartialNodeOutput,
    PredictiveBudgetGuard,
)

from app.schemas.graph_triage import (
    BudgetEstimateResponse,
    ExecutionSpendResponse,
    NodeExecutionOutputItem,
    PartialReduceResponse,
    SubtaskSpec,
    TriageAssessmentResponse,
    TriageFeaturesDTO,
)


class GraphTriageService:
    """Service managing task applicability triage, predictive budgeting, and early reduce."""

    _instance: ClassVar["GraphTriageService | None"] = None

    def __init__(self) -> None:
        self._gate = GraphApplicabilityTriageGate()
        self._budget_guard = PredictiveBudgetGuard()
        self._elastic_reducer = ElasticConcurrencyReducer()

    @classmethod
    def get_instance(cls) -> "GraphTriageService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def assess_task(
        self,
        prompt: str,
        subtasks: list[SubtaskSpec] | None = None,
    ) -> TriageAssessmentResponse:
        converted_subtasks: list[dict[str, list[str]]] | None = None
        if subtasks is not None:
            converted_subtasks = [
                {"id": st.id, "deps": st.deps, "heavy": st.heavy}  # type: ignore[dict-item]
                for st in subtasks
            ]

        decision = self._gate.evaluate(prompt, converted_subtasks)
        features_dto = TriageFeaturesDTO(
            prompt_length=decision.features.prompt_length,
            declared_subtasks_count=decision.features.declared_subtasks_count,
            independent_parallel_count=decision.features.independent_parallel_count,
            max_dependency_depth=decision.features.max_dependency_depth,
            is_conversational_inquiry=decision.features.is_conversational_inquiry,
            has_isolated_heavyweight_steps=decision.features.has_isolated_heavyweight_steps,
        )

        return TriageAssessmentResponse(
            verdict=decision.verdict.value,
            category=decision.category.value,
            reason=decision.reason,
            recommended_mode=decision.recommended_mode,
            estimated_speedup_ratio=decision.estimated_speedup_ratio,
            estimated_tokens_saved=decision.estimated_tokens_saved,
            features=features_dto,
        )

    def estimate_budget(
        self,
        node_count: int,
        fanout_concurrency: int,
        prompt_tokens: int = 1000,
        estimated_tokens_per_node: int = 15000,
        max_tokens_cap: int = 500_000,
        max_cost_usd_cap: float = 5.0,
    ) -> BudgetEstimateResponse:
        cfg = BudgetCapConfig(
            max_tokens=max_tokens_cap,
            max_cost_usd=max_cost_usd_cap,
        )
        res = self._budget_guard.estimate_budget(
            node_count=node_count,
            fanout_concurrency=fanout_concurrency,
            prompt_tokens=prompt_tokens,
            estimated_tokens_per_node=estimated_tokens_per_node,
            config=cfg,
        )

        return BudgetEstimateResponse(
            total_estimated_tokens=int(res["total_estimated_tokens"]),
            estimated_cost_usd=float(res["estimated_cost_usd"]),
            max_tokens_cap=int(res["max_tokens_cap"]),
            max_cost_usd_cap=float(res["max_cost_usd_cap"]),
            is_circuit_broken=bool(res["is_circuit_broken"]),
            recommendation=str(res["recommendation"]),
        )

    def configure_session(
        self,
        session_id: str,
        max_tokens: int = 500_000,
        max_cost_usd: float = 5.0,
        warning_threshold_pct: float = 0.3,
        critical_threshold_pct: float = 0.1,
        initial_concurrency: int = 4,
    ) -> ExecutionSpendResponse:
        cfg = BudgetCapConfig(
            max_tokens=max_tokens,
            max_cost_usd=max_cost_usd,
            warning_threshold_pct=warning_threshold_pct,
            critical_threshold_pct=critical_threshold_pct,
        )
        state = self._budget_guard.configure_session(
            session_id=session_id,
            config=cfg,
            initial_concurrency=initial_concurrency,
        )
        return ExecutionSpendResponse(
            session_id=state.session_id,
            current_tokens=state.current_tokens,
            current_cost_usd=state.current_cost_usd,
            remaining_tokens=state.remaining_tokens,
            remaining_budget_pct=state.remaining_budget_pct,
            budget_status=state.budget_status.value,
            active_concurrency=state.active_concurrency,
            is_throttled=state.is_throttled,
            is_circuit_broken=state.is_circuit_broken,
        )

    def update_spend(
        self,
        session_id: str,
        incremental_tokens: int,
        incremental_cost_usd: float | None = None,
    ) -> ExecutionSpendResponse:
        state = self._budget_guard.check_and_update_spend(
            session_id=session_id,
            incremental_tokens=incremental_tokens,
            incremental_cost_usd=incremental_cost_usd,
        )
        return ExecutionSpendResponse(
            session_id=state.session_id,
            current_tokens=state.current_tokens,
            current_cost_usd=state.current_cost_usd,
            remaining_tokens=state.remaining_tokens,
            remaining_budget_pct=state.remaining_budget_pct,
            budget_status=state.budget_status.value,
            active_concurrency=state.active_concurrency,
            is_throttled=state.is_throttled,
            is_circuit_broken=state.is_circuit_broken,
        )

    def get_spend_status(self, session_id: str) -> ExecutionSpendResponse:
        state = self._budget_guard.get_state(session_id)
        return ExecutionSpendResponse(
            session_id=state.session_id,
            current_tokens=state.current_tokens,
            current_cost_usd=state.current_cost_usd,
            remaining_tokens=state.remaining_tokens,
            remaining_budget_pct=state.remaining_budget_pct,
            budget_status=state.budget_status.value,
            active_concurrency=state.active_concurrency,
            is_throttled=state.is_throttled,
            is_circuit_broken=state.is_circuit_broken,
        )

    def perform_early_reduce(
        self,
        session_id: str,
        total_planned_tokens: int,
        nodes: list[NodeExecutionOutputItem],
    ) -> PartialReduceResponse:
        spend_state = self._budget_guard.get_state(session_id)
        harness_nodes = [
            PartialNodeOutput(
                node_id=n.node_id,
                status=n.status,
                result_summary=n.result_summary,
                tokens_used=n.tokens_used,
            )
            for n in nodes
        ]
        report = self._elastic_reducer.perform_graceful_early_reduce(
            session_id=session_id,
            spend_state=spend_state,
            node_outputs=harness_nodes,
            total_planned_tokens=total_planned_tokens,
        )
        return PartialReduceResponse(
            session_id=report.session_id,
            summary=report.summary,
            completed_nodes=report.completed_nodes,
            unexecuted_nodes=report.unexecuted_nodes,
            tokens_spent=report.tokens_spent,
            tokens_saved=report.tokens_saved,
            delivery_confidence=report.delivery_confidence,
            reason=report.reason,
        )
