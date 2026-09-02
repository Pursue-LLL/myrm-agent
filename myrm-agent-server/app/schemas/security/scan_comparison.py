"""Security vulnerability scan and run comparison Pydantic DTOs.

[INPUT]
- pydantic::BaseModel, ConfigDict, Field (POS: Data validation and serialization)

[OUTPUT]
- FindingItem, ScanRunSummary, ScanComparisonResult, FindingSeverity, FindingStatus

[POS]
Defines the schema contracts for agentic security findings, AST verification, and multi-run diff comparisons.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

FindingSeverity = Literal["critical", "high", "medium", "low", "info"]
FindingStatus = Literal["new", "persisting", "resolved", "regressed"]
ScanMode = Literal["diff", "full", "deep"]


class _CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class FindingItem(_CamelModel):
    """Represents an agentic security finding with optional PoC verification."""

    fingerprint: str = Field(
        description="Deterministic hash identifying the vulnerability signature across runs."
    )
    rule_id: str = Field(
        description="Internal rule identifier (e.g., sql-injection-concat)."
    )
    cwe: str = Field(
        default="CWE-Other", description="Standard Common Weakness Enumeration ID."
    )
    title: str = Field(
        description="Short human-readable title of the security finding."
    )
    severity: FindingSeverity = Field(default="high", description="Severity tier.")
    file_path: str = Field(description="Target file path containing the finding.")
    line_range: str | None = Field(
        default=None, description="Affected line numbers or span."
    )
    poc_command: str | None = Field(
        default=None, description="Executable PoC validation command."
    )
    poc_output: str | None = Field(
        default=None, description="Evidence output from PoC execution."
    )
    poc_verified: bool = Field(
        default=False, description="Whether the exploit was verified in sandbox."
    )
    fix_suggestion: str | None = Field(
        default=None, description="Actionable remediation code/guidance."
    )
    status: FindingStatus = Field(
        default="new", description="Lifecycle delta status relative to baseline run."
    )

    @classmethod
    def compute_fingerprint(
        cls, cwe: str, file_path: str, rule_id: str, signature: str = ""
    ) -> str:
        """Compute deterministic finding fingerprint to track lifecycle across code modifications."""
        norm_path = file_path.strip().replace("\\", "/").lower()
        raw_key = f"{cwe.upper()}:{rule_id.lower()}:{norm_path}:{signature.strip()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]


class ScanRunSummary(_CamelModel):
    """Snapshot metadata and findings for a single security scan execution."""

    run_id: str = Field(description="Unique scan run identifier.")
    session_id: str = Field(
        default="", description="Associated chat session ID if applicable."
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Run timestamp."
    )
    scan_mode: ScanMode = Field(
        default="diff", description="Execution mode: diff, full, or deep."
    )
    total_findings: int = Field(
        default=0, description="Total count of active findings."
    )
    critical_count: int = Field(default=0, description="Count of critical findings.")
    high_count: int = Field(default=0, description="Count of high findings.")
    medium_count: int = Field(default=0, description="Count of medium findings.")
    low_count: int = Field(default=0, description="Count of low findings.")
    poc_verified_count: int = Field(
        default=0, description="Count of verified PoC exploits."
    )
    findings: list[FindingItem] = Field(
        default_factory=list, description="List of findings in this run."
    )

    @classmethod
    def from_findings(
        cls,
        run_id: str,
        findings: list[FindingItem],
        session_id: str = "",
        scan_mode: ScanMode = "diff",
    ) -> ScanRunSummary:
        """Helper factory constructing summary aggregates from finding items."""
        critical = sum(1 for f in findings if f.severity == "critical")
        high = sum(1 for f in findings if f.severity == "high")
        medium = sum(1 for f in findings if f.severity == "medium")
        low = sum(1 for f in findings if f.severity == "low")
        poc_verified = sum(1 for f in findings if f.poc_verified)
        return cls(
            run_id=run_id,
            session_id=session_id,
            scan_mode=scan_mode,
            total_findings=len(findings),
            critical_count=critical,
            high_count=high,
            medium_count=medium,
            low_count=low,
            poc_verified_count=poc_verified,
            findings=findings,
        )


class ScanComparisonResult(_CamelModel):
    """Diff analysis between two scan runs tracking new, persisting, resolved, and regressed findings."""

    base_run_id: str | None = Field(
        default=None, description="Previous baseline run ID."
    )
    target_run_id: str = Field(description="Current target run ID.")
    new_findings: list[FindingItem] = Field(
        default_factory=list, description="Findings introduced in target run."
    )
    persisting_findings: list[FindingItem] = Field(
        default_factory=list, description="Findings present in both runs."
    )
    resolved_findings: list[FindingItem] = Field(
        default_factory=list,
        description="Findings present in base but fixed in target.",
    )
    regressed_findings: list[FindingItem] = Field(
        default_factory=list,
        description="Previously resolved findings that reappeared.",
    )
    total_delta: int = Field(
        default=0, description="Net difference in active findings."
    )
    summary_text: str = Field(default="", description="Human-readable delta summary.")
