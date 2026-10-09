"""Pydantic V2 schemas for CJK iteration mark disambiguation and recall matching API.

[POS]
Data transfer objects and request/response models for CJK ideographic iteration mark
('々') antecedent expansion, three-dimensional token sets, and recall scoring.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- DisambiguatedCjkTokensDTO
- IterationMarkRunDTO
- DisambiguateCjkRequest
- DisambiguateCjkResponse
- MatchCjkRecallRequest
- MatchCjkRecallResponse
- CjkIterationHealthResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DisambiguatedCjkTokensDTO(BaseModel):
    """Three-dimensional token matrix derived from CJK text with iteration marks."""

    raw_tokens: list[str] = Field(default_factory=list, description="Raw surface bigrams including '々'")
    normalized_tokens: list[str] = Field(default_factory=list, description="Expanded Han bigrams ('々' replaced)")
    anchor_tokens: list[str] = Field(default_factory=list, description="Contextual anchor bigrams around expanded indices")
    all_tokens: list[str] = Field(default_factory=list, description="Union of all valid lookup tokens")


class IterationMarkRunDTO(BaseModel):
    """Data transfer object for a single contiguous CJK character run."""

    raw_run: str = Field(description="Original contiguous CJK character slice")
    expanded_run: str = Field(description="Expanded CJK run with resolved antecedents")
    expanded_indices: list[int] = Field(default_factory=list, description="Indices where marks were expanded")
    raw_bigrams: list[str] = Field(default_factory=list, description="Raw bigrams")
    normalized_bigrams: list[str] = Field(default_factory=list, description="Normalized bigrams")
    anchor_bigrams: list[str] = Field(default_factory=list, description="Anchor bigrams")


class DisambiguateCjkRequest(BaseModel):
    """Request to resolve iteration marks across input text."""

    text: str = Field(min_length=1, description="CJK or mixed language text to disambiguate")


class DisambiguateCjkResponse(BaseModel):
    """Response detailing expanded text and token matrices."""

    original_text: str = Field(description="Original input text")
    normalized_text: str = Field(description="Resolved text with '々' replaced by antecedent Han")
    has_iteration_mark: bool = Field(description="Whether input contains '々' (U+3005)")
    marks_expanded_count: int = Field(ge=0, description="Total iteration marks successfully expanded")
    runs: list[IterationMarkRunDTO] = Field(default_factory=list, description="Parsed CJK runs")
    tokens: DisambiguatedCjkTokensDTO = Field(description="Three-dimensional token matrix")


class MatchCjkRecallRequest(BaseModel):
    """Request to compute recall match score between query and memory target."""

    query: str = Field(min_length=1, description="Search query")
    target_text: str = Field(min_length=1, description="Candidate memory text to match")
    threshold: float = Field(default=0.1, ge=0.0, le=1.0, description="Match decision threshold")


class MatchCjkRecallResponse(BaseModel):
    """Bidirectional recall matching verdict and breakdown."""

    query: str = Field(description="Search query")
    target: str = Field(description="Evaluated target memory text")
    is_matched: bool = Field(description="Whether score exceeds threshold with non-empty overlap")
    raw_overlap_count: int = Field(ge=0, description="Number of overlapping raw bigrams")
    normalized_overlap_count: int = Field(ge=0, description="Number of overlapping normalized bigrams")
    anchor_overlap_count: int = Field(ge=0, description="Number of overlapping anchor bigrams")
    composite_score: float = Field(ge=0.0, le=1.0, description="Weighted composite match score")
    matched_tokens: list[str] = Field(default_factory=list, description="List of matched token strings")


class CjkIterationHealthResponse(BaseModel):
    """Health check response for CJK iteration mark subsystem."""

    status: str = Field(default="ok")
    module: str = Field(default="cjk_iteration_mark")
    version: str = Field(default="1.0.0")
