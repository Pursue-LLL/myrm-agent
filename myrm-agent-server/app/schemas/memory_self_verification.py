"""
[POS] app/schemas/memory_self_verification.py
[INPUT] pydantic
[OUTPUT] FactMutationProbeRequestDTO, FactMutationProbeResponseDTO, ZeroLexicalProbeRequestDTO, ZeroLexicalProbeResponseDTO, ProceduralAntiDropProbeRequestDTO, ProceduralAntiDropProbeResponseDTO, RunDiagnosticSuiteRequestDTO, RunDiagnosticSuiteResponseDTO

Pydantic DTOs for Memory Self-Verification Diagnostic Suite and Fact Update Benchmark.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FactMutationProbeRequestDTO(BaseModel):
    """Payload to trigger in-place fact mutation & contradiction elimination probe."""

    model_config = ConfigDict(extra="forbid")

    entity_key: str = Field(default="monthly_revenue_target", description="Entity key or target slot")
    initial_fact: str = Field(default="当前核心战略目标为月入1万人民币", description="Initial fact statement")
    updated_fact: str = Field(default="战略目标已正式调整为月入3万人民币", description="Updated fact statement")


class FactMutationProbeResponseDTO(BaseModel):
    """Result of in-place fact mutation test asserting conflict elimination."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str = Field(..., description="Unique probe run ID")
    entity_key: str = Field(..., description="Target entity key")
    initial_fact: str = Field(..., description="Initial fact evaluated")
    updated_fact: str = Field(..., description="Updated fact evaluated")
    success: bool = Field(..., description="Whether mutation succeeded leaving 0 conflicts")
    retained_fact_count: int = Field(..., description="Active facts retained in storage")
    is_latest_retained: bool = Field(..., description="Whether the latest fact is accurately retained")
    residual_conflict_count: int = Field(..., description="Count of duplicate or conflicting facts")
    latency_ms: float = Field(..., description="Execution latency in milliseconds")
    details: str = Field(..., description="Human-readable probe execution details")


class ZeroLexicalProbeRequestDTO(BaseModel):
    """Payload to trigger zero-lexical-overlap semantic recall probe."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(default="靠什么赚钱", description="Query string with zero lexical overlap")
    memory_text: str = Field(default="在做 AI 教学、AI 工具、SEO", description="Target stored memory statement")
    min_similarity_threshold: float = Field(default=0.65, ge=0.0, le=1.0, description="Minimum cosine similarity")


class ZeroLexicalProbeResponseDTO(BaseModel):
    """Result of pure semantic recall test asserting zero surface word overlap."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str = Field(..., description="Unique probe run ID")
    query: str = Field(..., description="Query evaluated")
    memory_text: str = Field(..., description="Memory statement evaluated")
    lexical_overlap_ratio: float = Field(..., description="Jaccard word bag overlap ratio")
    is_zero_overlap: bool = Field(..., description="Strict assertion that lexical overlap equals 0.0")
    cosine_similarity: float = Field(..., description="Computed or simulated cosine similarity")
    recalled: bool = Field(..., description="Whether semantic recall succeeded under zero lexical overlap")
    latency_ms: float = Field(..., description="Execution latency in milliseconds")
    details: str = Field(..., description="Human-readable recall details")


class ProceduralAntiDropProbeRequestDTO(BaseModel):
    """Payload to trigger procedural routing & anti-silent drop test."""

    model_config = ConfigDict(extra="forbid")

    rule_content: str = Field(
        default="排查容器 503 报错时，必须优先检查端口映射与 IPv4 回环绑定，禁止直接重启服务",
        description="Troubleshooting rule or operational procedural specification",
    )


class ProceduralAntiDropProbeResponseDTO(BaseModel):
    """Result of procedural rule routing and anti-drop test."""

    model_config = ConfigDict(extra="forbid")

    probe_id: str = Field(..., description="Unique probe run ID")
    rule_content: str = Field(..., description="Rule evaluated")
    routed_track: str = Field(..., description="Target memory track (e.g. procedural)")
    was_dropped: bool = Field(..., description="Whether the rule was silently discarded")
    is_preserved: bool = Field(..., description="Whether the rule was successfully preserved")
    drop_reason: str | None = Field(default=None, description="Reason if rule was discarded")
    latency_ms: float = Field(..., description="Execution latency in milliseconds")
    details: str = Field(..., description="Human-readable probe outcome")


class RunDiagnosticSuiteRequestDTO(BaseModel):
    """Payload to execute complete four-dimensional diagnostic suite."""

    model_config = ConfigDict(extra="forbid")

    custom_namespace: str | None = Field(default=None, description="Optional isolated sandbox namespace")


class RunDiagnosticSuiteResponseDTO(BaseModel):
    """Comprehensive diagnostic benchmark report with guaranteed sandbox cleanup."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(..., description="Unique benchmark report identifier")
    sandbox_namespace: str = Field(..., description="Isolated sandbox namespace used")
    grade: str = Field(..., description="Health grade: EXCELLENT, GOOD, DEGRADED, CRITICAL")
    total_probes: int = Field(..., description="Total count of probes evaluated")
    passed_probes: int = Field(..., description="Count of passed probes")
    score: float = Field(..., description="Composite health score from 0.0 to 100.0")
    sandbox_cleaned: bool = Field(..., description="Whether test sandbox was completely purged")
    fact_mutation_result: FactMutationProbeResponseDTO = Field(..., description="Mutation probe outcome")
    zero_lexical_result: ZeroLexicalProbeResponseDTO = Field(..., description="Zero-lexical probe outcome")
    procedural_anti_drop_result: ProceduralAntiDropProbeResponseDTO = Field(..., description="Procedural probe outcome")
    mean_latency_ms: float = Field(..., description="Mean probe latency across suite")
    summary: str = Field(..., description="Actionable diagnostic summary")
