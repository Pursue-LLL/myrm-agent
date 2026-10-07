# [POS]: app/schemas/failure_search.py
# [INPUT]: None (Standard library & Pydantic)
# [OUTPUT]: ErrorFingerprintDTO, HistoricalResolutionEntryDTO, FailureRetrievalResultDTO, SearchFailureRequest, RecordHistoricalResolutionRequest, InterceptFailureRequest, InterceptFailureResponseDTO, FailureTriggerConfigDTO

"""Pydantic schemas and DTOs for failure-triggered historical session retrieval (Item 109)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorFingerprintDTO(BaseModel):
    """Data transfer object for extracted error fingerprint."""

    error_type: str = Field(description="Exception or failure class name")
    tool_name: str = Field(default="", description="Name of tool that triggered failure")
    normalized_pattern: str = Field(description="Scrubbed pattern without dynamic IDs/timestamps")
    exit_code: int | None = Field(default=None, description="Command exit code if shell execution")
    context_tags: list[str] = Field(default_factory=list, description="Categorical tags")


class HistoricalResolutionEntryDTO(BaseModel):
    """Data transfer object for an indexed historical resolution or cautionary attempt."""

    entry_id: str = Field(description="Unique index identifier")
    session_id: str = Field(description="Historical session identifier where resolution was discovered")
    turn_index: int = Field(default=0, description="Turn index containing the direct resolution")
    error_signature: str = Field(description="Error signature or pattern matched")
    outcome_type: str = Field(description="Outcome type: successful_resolution or cautionary_failure")
    solution_snippet: str = Field(description="Concrete command, patch, or workaround applied")
    explanation: str = Field(default="", description="Why this fix worked or why it failed")
    confidence: float = Field(default=1.0, description="Confidence score between 0.0 and 1.0")
    created_at: str = Field(description="ISO timestamp of creation")


class FailureRetrievalResultDTO(BaseModel):
    """Data transfer object for dual-track failure retrieval results."""

    query_fingerprint: ErrorFingerprintDTO = Field(description="Input query error fingerprint")
    total_matched: int = Field(default=0, description="Total matching historical entries")
    successful_resolutions: list[HistoricalResolutionEntryDTO] = Field(
        default_factory=list, description="Successful solutions from historical sessions"
    )
    cautionary_failures: list[HistoricalResolutionEntryDTO] = Field(
        default_factory=list, description="Cautionary failed attempts to prevent repeating dead ends"
    )
    suggested_action: str = Field(default="", description="Synthesized actionable recommendation")


class SearchFailureRequest(BaseModel):
    """Request payload to search historical resolutions for an error."""

    error_message: str = Field(description="Raw error output or exception trace")
    tool_name: str = Field(default="", description="Tool name where failure occurred")
    exit_code: int | None = Field(default=None, description="Exit code if applicable")
    top_n: int = Field(default=3, description="Maximum number of matches to retrieve per category")
    include_cautionary: bool = Field(default=True, description="Whether to include failed cautionary lessons")


class RecordHistoricalResolutionRequest(BaseModel):
    """Request payload to index a new historical resolution or cautionary lesson."""

    entry_id: str = Field(description="Unique entry identifier")
    session_id: str = Field(description="Originating session identifier")
    turn_index: int = Field(default=0, description="Turn index in session")
    error_signature: str = Field(description="Error signature or pattern")
    outcome_type: str = Field(
        default="successful_resolution",
        description="Outcome type: successful_resolution or cautionary_failure",
    )
    solution_snippet: str = Field(description="Actionable command, patch, or procedure applied")
    explanation: str = Field(default="", description="Explanation of resolution rationale")
    confidence: float = Field(default=1.0, description="Confidence score between 0.0 and 1.0")


class InterceptFailureRequest(BaseModel):
    """Request payload for failure interception and automated prompt injection."""

    tool_name: str = Field(description="Name of tool that failed")
    error_content: str = Field(description="Raw error output, traceback, or stderr")
    exit_code: int | None = Field(default=None, description="Command exit code if shell execution")


class InterceptFailureResponseDTO(BaseModel):
    """Response payload returning prompt-injected guidance upon failure."""

    should_inject: bool = Field(description="Whether a relevant historical resolution was found to inject")
    injected_prompt_block: str = Field(description="Formatted markdown block ready for LLM context injection")
    result: FailureRetrievalResultDTO | None = Field(
        default=None, description="Underlying retrieval result if matched"
    )


class FailureTriggerConfigDTO(BaseModel):
    """Configuration settings for automated failure-triggered retrieval."""

    enabled: bool = Field(default=True, description="Whether failure retrieval interception is active")
    auto_trigger_on_error: bool = Field(
        default=True, description="Whether to automatically search history without user prompt"
    )
    max_matches: int = Field(default=3, description="Maximum number of historical cases returned")
    min_similarity_threshold: float = Field(default=0.6, description="Minimum similarity score threshold")
    include_cautionary_failures: bool = Field(
        default=True, description="Whether to retrieve cautionary dead ends"
    )
