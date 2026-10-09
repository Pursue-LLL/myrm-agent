"""Business service coordinating Budget Greedy Marginal Value Recall Packing (Item 122).

[POS]
app/services/memory/budget_packing_service.py

[INPUT]
- app.schemas.budget_packing, myrm_agent_harness.toolkits.memory.budget_packing

[OUTPUT]
- BudgetPackingService, get_budget_packing_service
"""


from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory import (
    BilledTokenBudget,
    BudgetRecallPackingOrchestrator,
    DroppedCandidateItem,
    MarginalValueMetrics,
    PackedCandidateItem,
    PackedRecallResult,
    RecallCandidate,
    TokenAccountingReport,
    estimate_tokens,
)

from app.schemas.budget_packing import (
    BilledTokenBudgetDTO,
    DroppedCandidateItemDTO,
    InspectMarginalResponseItem,
    MarginalValueMetricsDTO,
    PackedCandidateItemDTO,
    PackedRecallResultDTO,
    RecallCandidateDTO,
    TokenAccountingReportDTO,
)

logger = logging.getLogger(__name__)


def _candidate_dto_to_domain(dto: RecallCandidateDTO) -> RecallCandidate:
    billed = dto.billed_tokens if dto.billed_tokens > 0 else estimate_tokens(dto.content)
    storage = dto.storage_tokens if dto.storage_tokens > 0 else billed
    return RecallCandidate(
        id=dto.id,
        content=dto.content,
        relevance_score=dto.relevance_score,
        confidence_score=dto.confidence_score,
        billed_tokens=billed,
        storage_tokens=storage,
        domain_tags=tuple(dto.domain_tags),
        source_session_id=dto.source_session_id,
    )


def _candidate_domain_to_dto(domain: RecallCandidate) -> RecallCandidateDTO:
    return RecallCandidateDTO(
        id=domain.id,
        content=domain.content,
        relevance_score=domain.relevance_score,
        confidence_score=domain.confidence_score,
        billed_tokens=domain.billed_tokens,
        storage_tokens=domain.storage_tokens,
        domain_tags=list(domain.domain_tags),
        source_session_id=domain.source_session_id,
    )


def _metrics_domain_to_dto(domain: MarginalValueMetrics) -> MarginalValueMetricsDTO:
    return MarginalValueMetricsDTO(
        base_utility=domain.base_utility,
        redundancy_score=domain.redundancy_score,
        marginal_info_gain=domain.marginal_info_gain,
        marginal_value=domain.marginal_value,
        marginal_value_density=domain.marginal_value_density,
    )


def _budget_dto_to_domain(dto: BilledTokenBudgetDTO | None) -> BilledTokenBudget:
    if dto is None:
        return BilledTokenBudget()
    return BilledTokenBudget(
        max_billed_tokens=dto.max_billed_tokens,
        diversity_penalty_lambda=dto.diversity_penalty_lambda,
        min_marginal_value_threshold=dto.min_marginal_value_threshold,
        max_redundancy_threshold=dto.max_redundancy_threshold,
        max_items_limit=dto.max_items_limit,
        allow_greedy_backfill=dto.allow_greedy_backfill,
    )


def _packed_item_domain_to_dto(domain: PackedCandidateItem) -> PackedCandidateItemDTO:
    return PackedCandidateItemDTO(
        candidate=_candidate_domain_to_dto(domain.candidate),
        metrics=_metrics_domain_to_dto(domain.metrics),
        order_index=domain.order_index,
        cumulative_billed_tokens=domain.cumulative_billed_tokens,
    )


def _dropped_item_domain_to_dto(domain: DroppedCandidateItem) -> DroppedCandidateItemDTO:
    return DroppedCandidateItemDTO(
        candidate=_candidate_domain_to_dto(domain.candidate),
        metrics=_metrics_domain_to_dto(domain.metrics),
        reason=domain.reason.value if hasattr(domain.reason, "value") else str(domain.reason),
    )


def _accounting_domain_to_dto(domain: TokenAccountingReport) -> TokenAccountingReportDTO:
    return TokenAccountingReportDTO(
        total_candidates_examined=domain.total_candidates_examined,
        items_packed_count=domain.items_packed_count,
        items_dropped_count=domain.items_dropped_count,
        billed_tokens_spent=domain.billed_tokens_spent,
        billed_tokens_budget=domain.billed_tokens_budget,
        billed_tokens_remaining=domain.billed_tokens_remaining,
        storage_tokens_total=domain.storage_tokens_total,
        storage_tokens_saved=domain.storage_tokens_saved,
        budget_utilization_pct=domain.budget_utilization_pct,
        redundant_tokens_filtered=domain.redundant_tokens_filtered,
        average_marginal_density=domain.average_marginal_density,
    )


def _packed_result_domain_to_dto(domain: PackedRecallResult) -> PackedRecallResultDTO:
    return PackedRecallResultDTO(
        packed_items=[_packed_item_domain_to_dto(item) for item in domain.packed_items],
        dropped_candidates=[_dropped_item_domain_to_dto(item) for item in domain.dropped_candidates],
        accounting=_accounting_domain_to_dto(domain.accounting),
        composed_prompt_block=domain.composed_prompt_block,
        active_mode=domain.active_mode,
    )


class BudgetPackingService:
    """Service facade for memory recall budget packing and marginal value evaluation."""

    def __init__(self, orchestrator: BudgetRecallPackingOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or BudgetRecallPackingOrchestrator()

    def pack_candidates(
        self,
        candidates: list[RecallCandidateDTO],
        budget: BilledTokenBudgetDTO | None = None,
        enable_knapsack: bool = True,
    ) -> PackedRecallResultDTO:
        """Execute greedy knapsack packing with token accounting and redundancy pruning."""
        domain_candidates = [_candidate_dto_to_domain(c) for c in candidates]
        domain_budget = _budget_dto_to_domain(budget)

        domain_result = self._orchestrator.pack_candidates(
            domain_candidates,
            budget=domain_budget,
            enable_knapsack=enable_knapsack,
        )
        return _packed_result_domain_to_dto(domain_result)

    def inspect_marginal_values(
        self,
        candidates: list[RecallCandidateDTO],
        budget: BilledTokenBudgetDTO | None = None,
    ) -> list[InspectMarginalResponseItem]:
        """Inspect sequential marginal value degradation for recall candidates."""
        domain_candidates = [_candidate_dto_to_domain(c) for c in candidates]
        domain_budget = _budget_dto_to_domain(budget)

        inspected = self._orchestrator.inspect_marginal_evaluation(
            domain_candidates,
            budget=domain_budget,
        )
        return [
            InspectMarginalResponseItem(
                candidate=_candidate_domain_to_dto(cand),
                metrics=_metrics_domain_to_dto(m),
            )
            for cand, m in inspected
        ]

    def get_default_budget(self) -> BilledTokenBudgetDTO:
        """Return recommended default budget parameters."""
        return BilledTokenBudgetDTO()


_budget_packing_service_instance: BudgetPackingService | None = None


def get_budget_packing_service() -> BudgetPackingService:
    """Dependency provider for BudgetPackingService."""
    global _budget_packing_service_instance
    if _budget_packing_service_instance is None:
        _budget_packing_service_instance = BudgetPackingService()
    return _budget_packing_service_instance
