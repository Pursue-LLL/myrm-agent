"""[INPUT] Pydantic models for Subagent Bounded Structured Failure Facts & Safe Diagnostic Protocol REST APIs.
[OUTPUT] Strong DTOs: AnalyzeFailureRequest, StructuredFailureFactDTO, AnalyzeFailureResponse, SubagentFailureHistoryResponse.
[POS] Public schema layer for subagent diagnostic failure facts subsystem.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AnalyzeFailureRequest(BaseModel):
    """Request payload to analyze, categorize, and scrub a subagent failure."""

    product: str = Field(..., description="Reporting subagent product name (e.g. codex-worker-01)")
    stage: str = Field(
        default="turn",
        description="Lifecycle stage: query-start / thread-start / turn-start / turn / process / teardown",
    )
    raw_message: str = Field(..., description="Raw error text or exception trace from subagent execution")
    category: Optional[str] = Field(
        default=None,
        description="Explicit failure category if known; otherwise automatically classified",
    )
    http_status: Optional[int] = Field(default=None, description="HTTP response code if applicable")
    exit_code: Optional[int] = Field(default=None, description="Process termination exit code if applicable")
    signal: Optional[str] = Field(default=None, description="POSIX signal string if applicable (e.g. SIGTERM)")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Custom metadata tags to be sanitized")


class StructuredFailureFactDTO(BaseModel):
    """Sanitized and machine-actionable structured failure fact payload."""

    product: str = Field(..., description="Subagent product identifier")
    stage: str = Field(..., description="Execution stage")
    category: str = Field(..., description="Classified error category")
    http_status: Optional[int] = Field(default=None, description="HTTP status")
    exit_code: Optional[int] = Field(default=None, description="Exit code")
    signal: Optional[str] = Field(default=None, description="Termination signal")
    sanitized_message: str = Field(..., description="Scrubbed and byte-bounded error summary")
    remediation: str = Field(..., description="Deterministic self-healing recommendation for parent orchestrator")
    safe_diagnostic_header: str = Field(..., description="Single-line standardized diagnostic header")
    byte_size: int = Field(..., description="Exact byte size conforming to <= 4096 bytes constraint")
    timestamp: float = Field(default_factory=time.time, description="Diagnosis timestamp")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Sanitized metadata")


class AnalyzeFailureResponse(BaseModel):
    """Response payload returning diagnosed structured failure fact."""

    fact: StructuredFailureFactDTO = Field(..., description="Diagnosed failure fact")


class SubagentFailureHistoryResponse(BaseModel):
    """Response payload listing recorded failure facts for a chat session."""

    total_count: int = Field(default=0, description="Total failures recorded")
    facts: List[StructuredFailureFactDTO] = Field(default_factory=list, description="List of recorded failure facts")
