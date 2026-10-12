"""
[POS] app/schemas/skill_health_audit.py
[INPUT] pydantic
[OUTPUT] Conversational skill health audit, taint sentinel, and SARIF DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AuditSkillRequestDTO(BaseModel):
    """Payload to trigger conversational skill health audit."""

    skill_name: str = Field(..., description="Unique name of the skill")
    code: str = Field(..., description="Python source code of the skill")
    frontmatter_str: str | None = Field(
        default=None,
        description="Optional declarative YAML frontmatter containing external_requests & provenance",
    )


class FourRowHealthCardDTO(BaseModel):
    """Plain-language 4-row security posture summary card."""

    source_credibility: str = Field(..., description="Origin trustworthiness: official, known, or unknown")
    file_boundary: str = Field(..., description="File access scope: internal memory, workspace, or system")
    network_egress: str = Field(..., description="Egress status: offline, declared-only, or suspicious leak")
    dangerous_syscalls: str = Field(..., description="OS execution status: clean or dangerous calls")


class TaintFlowFindingDTO(BaseModel):
    """Individual AST taint or exfiltration flow finding."""

    source_type: str = Field(..., description="Sensitive data source: sensitive_data, code, syscall")
    sink_type: str = Field(..., description="Target sink: HTTP/socket method or syscall")
    line_number: int = Field(..., description="Line number of the call")
    symbol: str = Field(..., description="Resolved AST symbol name")
    is_declared: bool = Field(..., description="Whether egress was declared in frontmatter")
    severity: str = Field(..., description="Severity tier: info, warning, high, critical_block")
    description: str = Field(..., description="Detailed diagnostic message")


class SkillHealthAuditVerdictDTO(BaseModel):
    """Comprehensive verdict returned by the skill health auditor."""

    skill_name: str = Field(..., description="Audited skill name")
    content_sha256: str = Field(..., description="SHA-256 digest of audited code")
    health_score: int = Field(..., description="Calculated 0-100 health score")
    is_clean: bool = Field(..., description="Whether skill passes clean audit bar")
    requires_attention: bool = Field(..., description="Whether caution or review is required")
    intel_status: str = Field(..., description="Intel status: verified_benign, known_malicious, unavailable_offline")
    plain_language_card: FourRowHealthCardDTO = Field(..., description="Four-row plain language card")
    taint_findings: list[TaintFlowFindingDTO] = Field(..., description="List of taint findings")
    declared_requests_count: int = Field(..., description="Number of declared endpoints")
    undeclared_sinks_count: int = Field(..., description="Number of undeclared network sinks")
    actionable_advice: str = Field(..., description="Anti-injection guidance and next steps")
    disclaimer: str = Field(..., description="Standard honest assessment disclaimer")
    raw_sarif: dict[str, str | int | list[dict[str, str | int]]] = Field(
        default_factory=dict, description="Standard SARIF 2.1.0 dictionary representation"
    )


class ExportSarifRequestDTO(BaseModel):
    """Payload to export SARIF 2.1.0 report for a skill."""

    skill_name: str = Field(..., description="Skill identifier")
    code: str = Field(..., description="Source code")
    frontmatter_str: str | None = Field(default=None, description="Optional frontmatter")


class SarifExportResponseDTO(BaseModel):
    """Standard SARIF 2.1.0 JSON report container."""

    skill_name: str = Field(..., description="Skill identifier")
    sarif_json: str = Field(..., description="Formatted SARIF 2.1.0 JSON string")


class RegisterMaliciousHashRequestDTO(BaseModel):
    """Payload to register a known malicious skill hash in local intel feed."""

    sha256_hash: str = Field(..., description="SHA-256 hash to blocklist")
