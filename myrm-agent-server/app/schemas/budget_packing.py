"""Pydantic schemas for Budget Greedy Marginal Value Recall Packing Suite (Item 122).

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- RecallCandidateDTO, BilledTokenBudgetDTO: packing inputs (scored candidate, billed-token budget with diversity penalty)
- MarginalValueMetricsDTO, PackedCandidateItemDTO, DroppedCandidateItemDTO, TokenAccountingReportDTO, PackedRecallResultDTO: packing outcome with per-item metrics and token accounting
- PackRecallRequest, InspectMarginalRequest, InspectMarginalResponseItem: endpoint payloads

[POS]
API contracts of budget-greedy recall packing, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecallCandidateDTO(BaseModel):
    """Candidate memory segment submitted for packing."""

    id: str = Field(..., description="Unique memory fragment ID")
    content: str = Field(..., description="Raw text content of the recalled memory")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Base retrieval relevance score")
    confidence_score: float = Field(1.0, ge=0.0, le=1.0, description="Confidence/verification score")
    billed_tokens: int = Field(0, ge=0, description="Tokens billed by LLM context injection")
    storage_tokens: int = Field(0, ge=0, description="Tokens stored in local index/storage")
    domain_tags: list[str] = Field(default_factory=list, description="Categorical or domain tags")
    source_session_id: str | None = Field(None, description="Originating session identifier")


class BilledTokenBudgetDTO(BaseModel):
    """Budget constraints and diversity hyper-parameters."""

    max_billed_tokens: int = Field(1000, ge=10, le=32000, description="Strict context token ceiling")
    diversity_penalty_lambda: float = Field(0.65, ge=0.0, le=1.0, description="Penalty weight for redundancy")
    min_marginal_value_threshold: float = Field(0.05, ge=0.0, le=1.0, description="Pruning threshold")
    max_redundancy_threshold: float = Field(0.45, ge=0.0, le=1.0, description="Hard ceiling for redundancy")
    max_items_limit: int = Field(15, ge=1, le=100, description="Max accepted memory items")
    allow_greedy_backfill: bool = Field(True, description="Backfill small items when top items overflow")


class MarginalValueMetricsDTO(BaseModel):
    """Marginal evaluation metrics snapshot for a candidate."""

    base_utility: float = Field(..., description="Base utility score (relevance * confidence)")
    redundancy_score: float = Field(..., description="Max Jaccard/n-gram overlap with accepted set")
    marginal_info_gain: float = Field(..., description="1.0 - lambda * redundancy_score")
    marginal_value: float = Field(..., description="Marginal value after diversity discount")
    marginal_value_density: float = Field(..., description="Marginal value per billed token")


class PackedCandidateItemDTO(BaseModel):
    """Accepted candidate in packed context."""

    candidate: RecallCandidateDTO
    metrics: MarginalValueMetricsDTO
    order_index: int
    cumulative_billed_tokens: int


class DroppedCandidateItemDTO(BaseModel):
    """Rejected candidate with explanation."""

    candidate: RecallCandidateDTO
    metrics: MarginalValueMetricsDTO
    reason: str = Field(..., description="Reason for rejection")


class TokenAccountingReportDTO(BaseModel):
    """Dual-track token accounting and savings report."""

    total_candidates_examined: int
    items_packed_count: int
    items_dropped_count: int
    billed_tokens_spent: int
    billed_tokens_budget: int
    billed_tokens_remaining: int
    storage_tokens_total: int
    storage_tokens_saved: int
    budget_utilization_pct: float
    redundant_tokens_filtered: int
    average_marginal_density: float


class PackedRecallResultDTO(BaseModel):
    """Aggregate result from greedy knapsack recall packing."""

    packed_items: list[PackedCandidateItemDTO]
    dropped_candidates: list[DroppedCandidateItemDTO]
    accounting: TokenAccountingReportDTO
    composed_prompt_block: str
    active_mode: str


class PackRecallRequest(BaseModel):
    """Request payload to pack candidates into recall context."""

    candidates: list[RecallCandidateDTO]
    budget: BilledTokenBudgetDTO | None = None
    enable_knapsack: bool = True


class InspectMarginalRequest(BaseModel):
    """Request payload to inspect marginal values sequentially."""

    candidates: list[RecallCandidateDTO]
    budget: BilledTokenBudgetDTO | None = None


class InspectMarginalResponseItem(BaseModel):
    """Inspection item breakdown."""

    candidate: RecallCandidateDTO
    metrics: MarginalValueMetricsDTO
