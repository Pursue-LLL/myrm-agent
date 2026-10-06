"""
[POS] app/schemas/code_memory_compaction.py
[INPUT] pydantic
[OUTPUT] CodeBlockInput, CompactedBlockOutput, CodeCompactionRequest, CodeCompactionResponse, SingleSkeletonRequest, SingleSkeletonResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CodeBlockInput(BaseModel):
    """Input representation of a code file or snippet to be compacted."""

    model_config = ConfigDict(extra="forbid")

    file_path: str = Field(..., min_length=1, description="Relative or absolute path of the code file")
    source_code: str = Field(..., description="Raw source code content")
    relevance_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Semantic relevance priority score"
    )
    language: str = Field(default="python", description="Programming language identifier")


class CompactedBlockOutput(BaseModel):
    """Compacted output representation of a single code block."""

    model_config = ConfigDict(extra="forbid")

    file_path: str
    abstraction_level: str
    content: str
    original_token_count: int
    compacted_token_count: int


class CodeCompactionRequest(BaseModel):
    """Request payload for multi-file token-budget-aware compaction."""

    model_config = ConfigDict(extra="forbid")

    items: list[CodeBlockInput] = Field(
        default_factory=list, description="List of code blocks to be compacted"
    )
    token_budget: int = Field(
        default=1500, ge=10, le=100000, description="Upper bound token quota"
    )
    min_level: str = Field(
        default="L1_SIGNATURES", description="Minimum allowed abstraction level"
    )
    strip_private_symbols: bool = Field(
        default=False, description="Whether to filter out private symbols"
    )
    tokens_per_char_ratio: float = Field(
        default=0.26, gt=0.0, le=2.0, description="Char-to-token heuristic ratio"
    )


class CodeCompactionResponse(BaseModel):
    """Aggregated response for token-budget-aware code memory compaction."""

    model_config = ConfigDict(extra="forbid")

    compacted_blocks: list[CompactedBlockOutput] = Field(
        default_factory=list, description="Rendered compacted blocks"
    )
    total_original_tokens: int = Field(ge=0, description="Sum of original token counts")
    total_compacted_tokens: int = Field(ge=0, description="Sum of compacted token counts")
    budget_limit: int = Field(ge=0, description="Assigned budget limit")
    compression_ratio: float = Field(ge=0.0, le=1.0, description="Relative reduction ratio")


class SingleSkeletonRequest(BaseModel):
    """Request payload to extract an AST skeleton from a single code snippet."""

    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(..., description="Raw source code snippet")
    level: str = Field(
        default="L1_SIGNATURES", description="Target abstraction tier (L1_SIGNATURES/L2_CONTROL_FLOW/L3_FULL_SOURCE)"
    )
    strip_private_symbols: bool = Field(
        default=False, description="Whether to filter out private symbols"
    )
    language: str = Field(default="python", description="Programming language identifier")


class SingleSkeletonResponse(BaseModel):
    """Response payload containing extracted skeleton for a single snippet."""

    model_config = ConfigDict(extra="forbid")

    abstraction_level: str
    content: str
    original_token_count: int
    compacted_token_count: int
