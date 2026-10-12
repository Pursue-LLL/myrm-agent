"""
[POS] app/schemas/live_session_credential_shield.py
[INPUT] pydantic, enum
[OUTPUT] AirlockChannelStatusResponse, SensitiveTargetTypeResponse, BoundingBoxSchema, BlindCredentialInputEventResponse, ScreenMaskRegionResponse, DOMRedactionRuleSchema, MaskingRedactionReportResponse, OpenAirlockRequest, CloseAirlockRequest, AirlockStatusResponse, RouteBlindInputRequest, RouteBlindInputResponse, RegisterMaskRegionRequest, RedactDOMRequest, RedactDOMResponse, HandoverScrubRequest, HandoverScrubResponse, LiveSessionShieldMetricsResponse

Pydantic schemas for Live Session Out-of-Band Credential Input Shield Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AirlockChannelStatusResponse(StrEnum):
    """Operational status of the out-of-band input airlock channel."""

    OPEN = "OPEN"
    LOCKED = "LOCKED"
    BLIND_ROUTING = "BLIND_ROUTING"
    CLOSED = "CLOSED"


class SensitiveTargetTypeResponse(StrEnum):
    """Classification of targeted confidential input elements."""

    PASSWORD_INPUT = "PASSWORD_INPUT"
    OTP_INPUT = "OTP_INPUT"
    API_KEY_FIELD = "API_KEY_FIELD"
    PAYMENT_CVV = "PAYMENT_CVV"
    GENERIC_CREDENTIAL = "GENERIC_CREDENTIAL"


class BoundingBoxSchema(BaseModel):
    """Rectangular pixel coordinate region on the screen."""

    x: int = Field(..., ge=0, description="X pixel coordinate")
    y: int = Field(..., ge=0, description="Y pixel coordinate")
    width: int = Field(..., gt=0, description="Bounding box pixel width")
    height: int = Field(..., gt=0, description="Bounding box pixel height")


class BlindCredentialInputEventResponse(BaseModel):
    """Event descriptor of keystrokes routed out-of-band without exposing raw secret."""

    session_id: str = Field(..., description="Target session identifier")
    target_selector: str = Field(..., description="Target DOM or control selector")
    target_type: SensitiveTargetTypeResponse = Field(..., description="Target element category")
    keystroke_count: int = Field(..., ge=0, description="Number of keystrokes routed")
    is_blind_routed: bool = Field(..., description="True if routed via out-of-band airlock")
    timestamp: float = Field(..., description="Epoch dispatch timestamp")


class ScreenMaskRegionResponse(BaseModel):
    """Screen region designated for opaque pixel masking."""

    region_id: str = Field(..., description="Mask region ID")
    box: BoundingBoxSchema = Field(..., description="Screen pixel bounds")
    mask_color: str = Field(default="#000000", description="Mask fill color hex")
    target_selector: str = Field(..., description="Selector of associated input")


class DOMRedactionRuleSchema(BaseModel):
    """Rule specifying DOM node attributes to redact prior to LLM observation."""

    selector_pattern: str = Field(..., min_length=1, description="Regex or CSS selector")
    attribute_to_redact: str = Field(default="value", description="Target attribute name")
    replacement_value: str = Field(
        default="<REDACTED_CREDENTIAL>",
        description="Safe placeholder replacement",
    )


class MaskingRedactionReportResponse(BaseModel):
    """Audit report generated upon session control handover back to Agent."""

    session_id: str = Field(..., description="Session identifier")
    masked_regions_count: int = Field(..., ge=0, description="Total screen regions masked")
    redacted_dom_nodes_count: int = Field(..., ge=0, description="Total DOM secret nodes scrubbed")
    observation_scrubbed: bool = Field(..., description="Whether observation view was sanitized")
    timestamp: float = Field(..., description="Audit timestamp")


class OpenAirlockRequest(BaseModel):
    """Payload to open an out-of-band airlock channel."""

    session_id: str = Field(..., min_length=1, description="Live session ID")


class CloseAirlockRequest(BaseModel):
    """Payload to close an out-of-band airlock channel."""

    session_id: str = Field(..., min_length=1, description="Live session ID")


class AirlockStatusResponse(BaseModel):
    """Status inquiry response of an airlock channel."""

    session_id: str = Field(..., description="Live session ID")
    status: AirlockChannelStatusResponse = Field(..., description="Current channel status")


class RouteBlindInputRequest(BaseModel):
    """Payload to dispatch sensitive keystrokes directly to target via out-of-band airlock."""

    session_id: str = Field(..., min_length=1, description="Target session ID")
    target_selector: str = Field(..., min_length=1, description="CSS or control selector")
    raw_secret: str = Field(..., min_length=1, description="Confidential keystroke value")
    target_type: SensitiveTargetTypeResponse | None = Field(
        default=None,
        description="Optional explicit sensitive input category",
    )


class RouteBlindInputResponse(BaseModel):
    """Result of out-of-band blind credential routing."""

    event: BlindCredentialInputEventResponse = Field(..., description="Blind event descriptor")
    dispatch_confirmation_id: str = Field(..., description="Dispatch confirmation token")


class RegisterMaskRegionRequest(BaseModel):
    """Payload to register a screen coordinate bounding box for masking."""

    session_id: str = Field(..., min_length=1, description="Live session ID")
    box: BoundingBoxSchema = Field(..., description="Target screen bounding box")
    target_selector: str = Field(..., min_length=1, description="Associated DOM selector")
    mask_color: str = Field(default="#000000", description="Mask color hex")


class RedactDOMRequest(BaseModel):
    """Payload to scrub confidential credentials and tokens from a DOM tree string."""

    dom_html: str = Field(..., description="Raw DOM HTML snapshot")
    custom_rules: list[DOMRedactionRuleSchema] | None = Field(
        default=None,
        description="Optional custom attribute redaction rules",
    )


class RedactDOMResponse(BaseModel):
    """Outcome of DOM credential redaction."""

    sanitized_dom: str = Field(..., description="Sanitized DOM HTML with tokens scrubbed")
    redacted_nodes_count: int = Field(..., ge=0, description="Total nodes and secrets redacted")


class HandoverScrubRequest(BaseModel):
    """Payload to execute atomic screen and DOM sanitization when returning control to Agent."""

    session_id: str = Field(..., min_length=1, description="Target session ID")
    dom_html: str = Field(..., description="Current DOM HTML snapshot")


class HandoverScrubResponse(BaseModel):
    """Outcome of atomic session control handover scrub."""

    sanitized_dom: str = Field(..., description="Sanitized DOM HTML safe for LLM context")
    report: MaskingRedactionReportResponse = Field(..., description="Handover audit report")


class LiveSessionShieldMetricsResponse(BaseModel):
    """Cumulative operational metrics for live session credential shield suite."""

    blind_inputs_routed_total: int = Field(..., ge=0)
    screen_masks_applied_total: int = Field(..., ge=0)
    dom_nodes_redacted_total: int = Field(..., ge=0)
    handover_scrubs_completed_total: int = Field(..., ge=0)
    prompt_injections_mitigated_total: int = Field(..., ge=0)
