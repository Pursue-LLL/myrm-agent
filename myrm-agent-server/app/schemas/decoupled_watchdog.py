"""
[POS] app/schemas/decoupled_watchdog.py
[INPUT] pydantic
[OUTPUT] WatchdogVerdictStatusEnum, ThreatSeverityEnum, FirewallSanitizeRequest, FirewallSanitizeResponse, WatchdogViolationDetailSchema, ActionContractSpecSchema, InvarianceAssertionRuleSchema, WatchdogInspectRequest, WatchdogInspectResponse, WatchdogMetricsResponse

Pydantic schemas for decoupled action watchdog and input firewall suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class WatchdogVerdictStatusEnum(StrEnum):
    """Verdict decision made by the decoupled watchdog."""

    APPROVED = "approved"
    BLOCKED = "blocked"
    CIRCUIT_BREAKER_TRIGGERED = "circuit_breaker_triggered"
    NEEDS_CONFIRMATION = "needs_confirmation"


class ThreatSeverityEnum(StrEnum):
    """Threat severity enumeration."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FirewallSanitizeRequest(BaseModel):
    """Request payload for sanitizing inbound external multimodal content."""

    raw_content: str = Field(..., description="Raw HTML, markdown, or plain text from external source.")
    source_type: str = Field(default="web_page", description="Source classification (web_page, email, doc).")


class FirewallSanitizeResponse(BaseModel):
    """Response payload containing sanitized content and telemetry."""

    source_type: str = Field(..., description="Source classification.")
    sanitized_content: str = Field(..., description="Defanged and sanitized content safe for LLM vision.")
    hidden_text_stripped_count: int = Field(..., ge=0, description="Total hidden/invisible characters removed.")
    has_markdown_injection: bool = Field(..., description="Whether system tag injection attempts were defanged.")
    stripped_tags: list[str] = Field(default_factory=list, description="Categories of stripped tags.")
    latency_ms: float = Field(..., ge=0.0, description="Processing latency in milliseconds.")


class WatchdogViolationDetailSchema(BaseModel):
    """Structured detail of an invariant assertion failure."""

    violation_type: str = Field(..., description="Category of invariant failure.")
    threat_severity: ThreatSeverityEnum = Field(..., description="Threat severity level.")
    description: str = Field(..., description="Human-readable violation summary.")
    parameter_key: str = Field(default="", description="Target parameter triggering violation.")
    observed_value: str = Field(default="", description="Value passed in arguments.")
    expected_constraint: str = Field(default="", description="Expected invariant contract boundary.")


class ActionContractSpecSchema(BaseModel):
    """Specification of a proposed tool action inspected by the watchdog."""

    action_id: str = Field(..., min_length=1, max_length=128, description="Action identifier.")
    tool_name: str = Field(..., min_length=1, max_length=100, description="Name of the tool.")
    arguments: dict[str, str | int | float | bool | list[str]] = Field(
        ..., description="Tool arguments map."
    )
    user_original_intent: str = Field(..., description="User's original prompt / task intent.")
    caller_role: str = Field(default="assistant", description="Originating role proposing action.")
    snapshot_context: dict[str, str] = Field(default_factory=dict, description="Environmental state.")


class InvarianceAssertionRuleSchema(BaseModel):
    """Explicit safety invariants configured for high-consequence tools."""

    rule_name: str = Field(..., min_length=1, max_length=100, description="Rule identifier.")
    target_tool: str = Field(..., min_length=1, max_length=100, description="Target tool name.")
    max_amount_limit: float = Field(default=0.0, ge=0.0, description="Max amount limit if financial.")
    allowed_recipients: list[str] = Field(default_factory=list, description="Allowlist for external destinations.")
    prohibited_destinations: list[str] = Field(default_factory=list, description="Blacklist for destinations.")
    strict_intent_binding: bool = Field(default=True, description="Enforce strict intent-parameter binding.")


class WatchdogInspectRequest(BaseModel):
    """Request payload for inspecting an action prior to execution."""

    action: ActionContractSpecSchema = Field(..., description="Proposed action specification.")
    rule: InvarianceAssertionRuleSchema | None = Field(default=None, description="Optional invariance rule.")


class WatchdogInspectResponse(BaseModel):
    """Response payload from the decoupled watchdog daemon."""

    action_id: str = Field(..., description="Evaluated action ID.")
    verdict: WatchdogVerdictStatusEnum = Field(..., description="Watchdog verdict.")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score.")
    violations: list[WatchdogViolationDetailSchema] = Field(default_factory=list, description="Violations list.")
    circuit_breaker_active: bool = Field(..., description="Whether the circuit breaker was tripped.")
    latency_ms: float = Field(..., ge=0.0, description="Inspection latency in milliseconds.")
    rationale: str = Field(default="", description="Detailed audit justification.")


class WatchdogMetricsResponse(BaseModel):
    """Operational telemetry and mitigation metrics for decoupled watchdog."""

    total_inspected_actions: int = Field(..., ge=0, description="Total actions audited by watchdog.")
    approved_actions: int = Field(..., ge=0, description="Total approved actions.")
    blocked_actions: int = Field(..., ge=0, description="Total blocked/rejected actions.")
    circuit_breaker_trips: int = Field(..., ge=0, description="Total times circuit breaker tripped.")
    confirmation_required_count: int = Field(..., ge=0, description="Actions needing human confirmation.")
    total_sanitized_inputs: int = Field(..., ge=0, description="Total inbound inputs sanitized by firewall.")
    avg_latency_ms: float = Field(..., ge=0.0, description="Average inspection latency in ms.")
