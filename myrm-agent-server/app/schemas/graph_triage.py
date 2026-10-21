from pydantic import BaseModel, Field


class SubtaskSpec(BaseModel):
    id: str = Field(min_length=1, description="Unique subtask identifier")
    deps: list[str] = Field(default_factory=list, description="List of dependency subtask ids")
    heavy: bool = Field(default=False, description="Whether subtask is computationally heavy")


class TriageAssessmentRequest(BaseModel):
    prompt: str = Field(min_length=1, description="Prompt text to evaluate")
    subtasks: list[SubtaskSpec] | None = Field(default=None, description="Explicit subtasks DAG if available")


class TriageFeaturesDTO(BaseModel):
    prompt_length: int
    declared_subtasks_count: int
    independent_parallel_count: int
    max_dependency_depth: int
    is_conversational_inquiry: bool
    has_isolated_heavyweight_steps: bool


class TriageAssessmentResponse(BaseModel):
    verdict: str
    category: str
    reason: str
    recommended_mode: str
    estimated_speedup_ratio: float
    estimated_tokens_saved: int
    features: TriageFeaturesDTO


class BudgetEstimateRequest(BaseModel):
    node_count: int = Field(default=1, ge=1)
    fanout_concurrency: int = Field(default=1, ge=1)
    prompt_tokens: int = Field(default=1000, ge=0)
    estimated_tokens_per_node: int = Field(default=15000, ge=100)
    max_tokens_cap: int = Field(default=500_000, ge=1000)
    max_cost_usd_cap: float = Field(default=5.0, ge=0.01)


class BudgetEstimateResponse(BaseModel):
    total_estimated_tokens: int
    estimated_cost_usd: float
    max_tokens_cap: int
    max_cost_usd_cap: float
    is_circuit_broken: bool
    recommendation: str


class ConfigureGuardRequest(BaseModel):
    max_tokens: int = Field(default=500_000, ge=1000)
    max_cost_usd: float = Field(default=5.0, ge=0.01)
    warning_threshold_pct: float = Field(default=0.3, ge=0.01, le=0.9)
    critical_threshold_pct: float = Field(default=0.1, ge=0.001, le=0.5)
    initial_concurrency: int = Field(default=4, ge=1)


class SpendUpdateRequest(BaseModel):
    incremental_tokens: int = Field(default=0, ge=0)
    incremental_cost_usd: float | None = Field(default=None, ge=0.0)


class ExecutionSpendResponse(BaseModel):
    session_id: str
    current_tokens: int
    current_cost_usd: float
    remaining_tokens: int
    remaining_budget_pct: float
    budget_status: str
    active_concurrency: int
    is_throttled: bool
    is_circuit_broken: bool


class NodeExecutionOutputItem(BaseModel):
    node_id: str
    status: str
    result_summary: str = Field(default="")
    tokens_used: int = Field(default=0, ge=0)


class PartialReduceRequest(BaseModel):
    total_planned_tokens: int = Field(ge=1000)
    nodes: list[NodeExecutionOutputItem] = Field(default_factory=list)


class PartialReduceResponse(BaseModel):
    session_id: str
    summary: str
    completed_nodes: list[str]
    unexecuted_nodes: list[str]
    tokens_spent: int
    tokens_saved: int
    delivery_confidence: float
    reason: str
