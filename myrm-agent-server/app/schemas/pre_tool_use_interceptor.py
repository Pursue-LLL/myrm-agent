"""Pydantic schemas for PreToolUse Hook Interceptor & API Key Precedence.

[INPUT]
- Web requests inspecting proposed tool invocations and checking API key billing precedence.

[OUTPUT]
- Serialized verdicts, hard gate security rejections, and billing conflict warnings.

[POS]
- Server-side DTO contracts for soft prompt vs hard invariant decoupling.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HardRuleSpecDto(BaseModel):
    """Specification of an immutable pre-tool use security rule."""

    rule_id: str = Field(description="Unique rule identifier")
    category: str = Field(description="Rule category")
    pattern: str = Field(description="Regular expression pattern matched against payload")
    description: str = Field(description="Rule explanation")
    enabled: bool = Field(default=True, description="Whether rule is currently active")


class InterceptToolUseRequest(BaseModel):
    """Request payload to inspect tool execution before dispatch."""

    tool_name: str = Field(description="Tool being invoked (e.g., 'run_command', 'write_to_file')")
    payload_str: str = Field(description="String representation of execution payload")
    raise_on_block: bool = Field(
        default=False, description="Whether to raise HTTP 403 upon hard gate block"
    )


class InterceptToolUseResponse(BaseModel):
    """Inspection verdict produced by pre-tool dispatch gate."""

    verdict: str = Field(description="'ALLOW' or 'BLOCK'")
    blocked_rule_id: str | None = Field(default=None, description="Triggered rule ID if blocked")
    rule_category: str | None = Field(default=None, description="Category of breached invariant")
    rejection_reason: str | None = Field(default=None, description="Reason if blocked")
    detected_pattern: str | None = Field(default=None, description="Regex pattern matched")


class DetectApiKeyConflictRequest(BaseModel):
    """Request payload to detect ambient environment variable billing conflicts."""

    active_provider: str = Field(
        description="Active provider identifier (e.g. 'anthropic', 'openai')"
    )
    is_subscription_route: bool = Field(
        default=True, description="True if user selected a flat subscription route"
    )
    env_dict: dict[str, str] | None = Field(
        default=None, description="Optional custom environment mapping to test"
    )


class DetectApiKeyConflictResponse(BaseModel):
    """Audit outcome for ambient environment key precedence conflicts."""

    has_conflict: bool = Field(description="True if ambient key poses silent surcharge risk")
    detected_env_vars: list[str] = Field(
        default_factory=list, description="Conflicting environment variables found"
    )
    active_provider: str = Field(description="Target provider evaluated")
    warning_message: str | None = Field(default=None, description="Warning explanation")
    recommended_action: str | None = Field(default=None, description="Guidance to resolve conflict")


class ToggleRuleRequest(BaseModel):
    """Request payload to enable or disable a hard invariant rule."""

    rule_id: str = Field(description="Target rule ID")
    enabled: bool = Field(description="Desired enabled status")
