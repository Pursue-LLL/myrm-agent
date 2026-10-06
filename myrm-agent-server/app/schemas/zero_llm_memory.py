"""
[POS] app/schemas/zero_llm_memory.py
[INPUT] pydantic
[OUTPUT] ZeroLlmFactDTO, ZeroLlmExtractRequest, ZeroLlmExtractResponse, ZeroLlmSearchRequest, ZeroLlmSearchHitDTO, ZeroLlmSearchResponse, ZeroLlmStatsResponse

Pydantic schemas for Zero-LLM deterministic local memory capture and FTS graph retrieval.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ZeroLlmFactDTO(BaseModel):
    """Data transfer object representing a fact extracted with zero LLM tokens."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Unique deterministic identifier for the extracted fact")
    category: str = Field(..., description="Fact category: preference, configuration, tool_outcome, decision, entity, dependency")
    subject: str = Field(..., description="Subject of the fact")
    predicate: str = Field(..., description="Predicate relationship or action")
    object_value: str = Field(..., description="Target value or state")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Rule-based confidence score")
    evidence_snippet: str = Field(..., description="Verbatim textual evidence triggering the rule")
    source_turn_index: int = Field(default=0, ge=0, description="Turn index where fact was discovered")
    source_file: str | None = Field(default=None, description="Optional source file or tool reference")


class ZeroLlmExtractRequest(BaseModel):
    """Payload to trigger deterministic zero-cost memory extraction from text."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, description="Input text, command output, or conversation turn")
    turn_index: int = Field(default=0, ge=0, description="Turn index for tracking context recency")
    source_file: str | None = Field(default=None, description="Optional file path or command identifier")


class ZeroLlmExtractResponse(BaseModel):
    """Response containing extracted memory facts with zero-cost guarantee."""

    model_config = ConfigDict(extra="forbid")

    facts: list[ZeroLlmFactDTO] = Field(default_factory=list, description="Extracted fact collection")
    total_extracted: int = Field(ge=0, description="Total count of unique facts extracted")
    zero_token_cost: bool = Field(default=True, description="True verifying zero model token consumption")


class ZeroLlmSearchRequest(BaseModel):
    """Payload to search memory via SQLite FTS5 lexical matching and 1-hop graph traversal."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Search query keywords")
    profile_id: str | None = Field(default=None, description="Optional agent profile ID filter")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum returned matching items")
    graph_hop_decay: float = Field(default=0.5, ge=0.1, le=1.0, description="Topological distance decay factor")


class ZeroLlmSearchHitDTO(BaseModel):
    """Individual search match combining FTS5 lexical score and graph topology distance."""

    model_config = ConfigDict(extra="forbid")

    page_slug: str = Field(..., description="Wiki memory page slug")
    title: str = Field(..., description="Page title")
    snippet: str = Field(..., description="Excerpt snippet")
    fts_score: float = Field(..., description="FTS5 normalized lexical score")
    graph_hops: int = Field(..., ge=0, description="Topological hop distance (0=direct hit, 1=wikilink neighbor)")
    composite_score: float = Field(..., description="Unified ranking score considering decay")
    linked_entities: list[str] = Field(default_factory=list, description="Wikilink targets extracted from page")


class ZeroLlmSearchResponse(BaseModel):
    """Response containing ranked search matches from zero-token retrieval."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Original search query string")
    hits: list[ZeroLlmSearchHitDTO] = Field(default_factory=list, description="Ranked hit collection")
    total_hits: int = Field(ge=0, description="Total matching documents found")
    zero_token_cost: bool = Field(default=True, description="True verifying zero model token consumption")


class ZeroLlmStatsResponse(BaseModel):
    """Operational telemetry and zero-cost verification statistics."""

    model_config = ConfigDict(extra="forbid")

    total_extractions: int = Field(ge=0, description="Total facts extracted over service lifecycle")
    total_queries: int = Field(ge=0, description="Total search queries handled")
    zero_token_cost: bool = Field(default=True, description="True confirming zero model tokens consumed")
    augmentation_mode: str = Field(..., description="Current progressive enhancement mode")
    llm_available: bool = Field(..., description="Whether active LLM credentials are detected")
    min_confidence: float = Field(..., description="Minimum extraction confidence threshold")
    graph_hop_decay: float = Field(..., description="Graph neighbor hop decay factor")
