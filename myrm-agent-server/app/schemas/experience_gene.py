"""
[POS] app/schemas/experience_gene.py
[INPUT] pydantic
[OUTPUT] ExecutionStepInput, MultiTurnTraceInput, ExperienceGeneResponse, ExtractGeneRequest, ExtractGeneResponse, GeneAdviceRequest, GeneMutationAdviceResponse, GeneAdviceListResponse, GenePenalizeRequest, GeneLedgerStatsResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExecutionStepInput(BaseModel):
    """Execution step detail in a multi-turn task trace."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(..., ge=1, description="Sequential step index")
    tool_name: str = Field(..., min_length=1, description="Executed tool name")
    tool_input_summary: str = Field(..., description="Summary of input arguments")
    tool_output_snippet: str = Field(default="", description="Output snippet or error")
    is_failure: bool = Field(default=False, description="Whether this step resulted in failure")
    error_signature: str = Field(default="", description="Sanitized or raw error message")


class MultiTurnTraceInput(BaseModel):
    """Multi-turn task trace payload for causal gene extraction."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., min_length=1, description="Unique session identifier")
    task_goal: str = Field(..., min_length=1, description="User task goal or prompt")
    steps: list[ExecutionStepInput] = Field(default_factory=list, description="Ordered steps")
    success_verified: bool = Field(default=True, description="Whether the task ended in verified success")
    final_solution_summary: str = Field(default="", description="Summary of the verified resolution")
    domain_tag: str = Field(default="debugging", description="Domain classification tag")


class ExperienceGeneResponse(BaseModel):
    """Causal experience gene representation."""

    model_config = ConfigDict(extra="forbid")

    gene_id: str
    trigger_signals: list[str]
    hypotheses_refuted: list[str]
    proven_resolution: str
    polarity: str
    confidence_score: float
    proof_count: int
    provenance_session_id: str
    tags: list[str]
    created_at: float
    updated_at: float


class ExtractGeneRequest(BaseModel):
    """Request payload to extract and record a causal gene from a trace."""

    model_config = ConfigDict(extra="forbid")

    trace: MultiTurnTraceInput


class ExtractGeneResponse(BaseModel):
    """Response returned upon gene extraction and ledger recording."""

    model_config = ConfigDict(extra="forbid")

    status: str
    gene: ExperienceGeneResponse | None = None
    reinforced: bool = False


class GeneAdviceRequest(BaseModel):
    """Request payload to query gene-informed planning mutation advice."""

    model_config = ConfigDict(extra="forbid")

    active_signals: list[str] = Field(
        default_factory=list, description="Active context symptoms or error signals"
    )
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0, description="Minimum confidence")
    limit: int = Field(default=5, ge=1, le=50, description="Maximum returned items")


class GeneMutationAdviceResponse(BaseModel):
    """Actionable planning advice to preempt dead-ends and steer towards verified resolutions."""

    model_config = ConfigDict(extra="forbid")

    gene_id: str
    matched_signals: list[str]
    refuted_paths: list[str]
    recommended_resolution: str
    confidence: float
    polarity: str


class GeneAdviceListResponse(BaseModel):
    """List of generated planning mutation advices."""

    model_config = ConfigDict(extra="forbid")

    advices: list[GeneMutationAdviceResponse] = Field(default_factory=list)
    total_matched: int = Field(ge=0)


class GenePenalizeRequest(BaseModel):
    """Request payload to penalize an ineffective gene."""

    model_config = ConfigDict(extra="forbid")

    gene_id: str = Field(..., min_length=1)
    penalty: float = Field(default=0.2, gt=0.0, le=1.0)


class GeneLedgerStatsResponse(BaseModel):
    """Summary statistics of the experience gene ledger."""

    model_config = ConfigDict(extra="forbid")

    total_genes: int = Field(ge=0)
    avg_confidence: float = Field(ge=0.0, le=1.0)
    total_proof_count: int = Field(ge=0)
