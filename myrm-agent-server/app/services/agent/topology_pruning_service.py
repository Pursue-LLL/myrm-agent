"""Service layer for Model-Tier Adaptive Topology Pruning and folding evaluation.

[INPUT]
- myrm_agent_harness.agent.dynamic_workflow.topology_pruner::(
    ModelIntelligenceTier,
    ModelTierAdaptiveTopologyPruner,
    PruningDecisionKind,
    PruningStrategy,
    TaskComplexityLevel,
    TopologyPruningEvaluation,
    get_topology_pruner,
  )
- pydantic::BaseModel, Field

[OUTPUT]
- TopologyPruningService: High-level server service providing pruning evaluation and model tier catalog.
- PruneEvaluationRequest: Input DTO for task topology pruning assessment.
- PruneEvaluationResponse: Output DTO containing pruning decision, saved turns/tokens, and rationale.
- ModelTierCatalogItem: Known model intelligence hierarchy entry.
- ModelTierCatalogResponse: List of model tier definitions and representative benchmarks.

[POS]
Server-side service orchestrating DSH-style topology simplification based on active model intelligence.
"""

from __future__ import annotations

from myrm_agent_harness.agent.dynamic_workflow.topology_pruner import (
    ModelIntelligenceTier,
    ModelTierAdaptiveTopologyPruner,
    PruningDecisionKind,
    PruningStrategy,
    TaskComplexityLevel,
    TopologyPruningEvaluation,
    get_topology_pruner,
)
from pydantic import BaseModel, Field


class PruneEvaluationRequest(BaseModel):
    """Input payload to evaluate topology pruning for a task."""

    task_description: str
    model_name: str
    explicit_tier: ModelIntelligenceTier | None = None
    strategy: PruningStrategy = "auto"
    planned_subtasks_count: int = Field(default=3, ge=1, le=50)


class PruneEvaluationResponse(BaseModel):
    """Output payload with pruning recommendation and estimated savings."""

    decision: PruningDecisionKind
    model_name: str
    model_tier: ModelIntelligenceTier
    strategy: PruningStrategy
    task_complexity: TaskComplexityLevel
    is_folded: bool
    rationale: str
    planned_subtasks_count: int
    executed_subtasks_count: int
    estimated_saved_turns: int
    estimated_saved_tokens: int


class ModelTierCatalogItem(BaseModel):
    """Descriptor of a model intelligence tier and representative models."""

    tier: ModelIntelligenceTier
    display_name: str
    description: str
    recommended_pruning_mode: str
    representative_models: list[str]


class ModelTierCatalogResponse(BaseModel):
    """Catalog of supported model intelligence tiers and folding guidelines."""

    tiers: list[ModelTierCatalogItem]
    total_tiers: int


_KNOWN_TIERS: list[ModelTierCatalogItem] = [
    ModelTierCatalogItem(
        tier="tier_1_sota_reasoning",
        display_name="Tier 1 · SOTA Long Reasoning",
        description="High-intelligence deep reasoning models capable of resolving multi-step tasks in a single run.",
        recommended_pruning_mode="Aggressive folding to direct single-agent execution",
        representative_models=[
            "claude-3-7-sonnet",
            "claude-3-5-sonnet",
            "deepseek-r1",
            "deepseek-v3",
            "deepseek-v4-pro",
            "gpt-5",
            "gpt-4o",
            "o1",
            "o3",
        ],
    ),
    ModelTierCatalogItem(
        tier="tier_2_strong_base",
        display_name="Tier 2 · Strong Base",
        description="Balanced instruction and general foundation models requiring decomposition for complex tasks.",
        recommended_pruning_mode="Selective folding for low/medium tasks; fanout for high complexity",
        representative_models=[
            "claude-3-5-haiku",
            "gpt-4o-mini",
            "deepseek-v4",
            "qwen-2.5-32b",
            "qwen-2.5-72b",
            "llama-3.3-70b",
        ],
    ),
    ModelTierCatalogItem(
        tier="tier_3_fast_light",
        display_name="Tier 3 · Fast Light",
        description="Lightweight and local edge models requiring explicit multi-agent task breakdown to preserve accuracy.",
        recommended_pruning_mode="Full multi-agent fanout delegation preserved",
        representative_models=[
            "qwen-2.5-7b",
            "llama-3-8b",
            "deepseek-v4-flash",
            "gpt-3.5-turbo",
            "phi-4",
        ],
    ),
]


class TopologyPruningService:
    """Business service providing topology pruning evaluation and catalog lookups."""

    def __init__(self, pruner: ModelTierAdaptiveTopologyPruner | None = None) -> None:
        self._pruner = pruner or get_topology_pruner()

    def evaluate_pruning(self, req: PruneEvaluationRequest) -> PruneEvaluationResponse:
        """Evaluate task and model tier to generate topology pruning recommendation."""
        res: TopologyPruningEvaluation = self._pruner.evaluate_pruning(
            task_description=req.task_description,
            model_name=req.model_name,
            explicit_tier=req.explicit_tier,
            strategy=req.strategy,
            planned_subtasks_count=req.planned_subtasks_count,
        )

        return PruneEvaluationResponse(
            decision=res.decision,
            model_name=res.model_name,
            model_tier=res.model_tier,
            strategy=res.strategy,
            task_complexity=res.task_complexity,
            is_folded=res.is_folded,
            rationale=res.rationale,
            planned_subtasks_count=res.planned_subtasks_count,
            executed_subtasks_count=res.executed_subtasks_count,
            estimated_saved_turns=res.estimated_saved_turns,
            estimated_saved_tokens=res.estimated_saved_tokens,
        )

    def get_tier_catalog(self) -> ModelTierCatalogResponse:
        """Retrieve list of model intelligence tiers and adaptive pruning guidance."""
        return ModelTierCatalogResponse(
            tiers=_KNOWN_TIERS,
            total_tiers=len(_KNOWN_TIERS),
        )
