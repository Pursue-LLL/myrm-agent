"""Channel Pairing & Handshake Protocol Types.

[INPUT]
- pydantic: BaseModel, Field
- enum: Enum

[OUTPUT]
- ChannelPlatform: Enum of supported external channels for pairing
- PairingStatus: Enum of pairing lifecycle states
- PairingSessionCreateRequest: Schema to initialize pairing session
- PairingQRCode: Schema representing generated dynamic QR code and payload
- PairingSessionResponse: Schema representing pairing session details
- PairingConfirmRequest: Schema to simulate or submit scan callback token
- PairingConfirmResponse: Schema confirming token binding
- ChannelPingRequest: Schema for one-click ping connectivity probe
- ChannelPingResponse: Schema reporting delivery latency and receipt

[POS]
Data contract for model-agnostic external channel token binding and visual pairing wizard.
Decouples channel setup from LLM conversation turns and cognitive capability.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class ChannelPlatform(str, Enum):
    """External channel platforms supporting visual pairing wizard."""

    WECHAT = "wechat"
    WECOM = "wecom"
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    SLACK = "slack"
    TELEGRAM = "telegram"


class PairingStatus(str, Enum):
    """Lifecycle status of a channel visual pairing session."""

    PENDING = "pending"
    SCANNED = "scanned"
    AUTHENTICATED = "authenticated"
    FAILED = "failed"
    EXPIRED = "expired"


class PairingSessionCreateRequest(BaseModel):
    """Request model to initiate a visual pairing session."""

    platform: ChannelPlatform = Field(..., description="Target external channel platform")
    channel_instance_id: str | None = Field(
        default=None,
        description="Optional existing channel instance identifier to bind",
    )
    custom_label: str | None = Field(
        default=None,
        description="Optional human-friendly display label",
    )


class PairingQRCode(BaseModel):
    """Dynamic QR code and pairing payload."""

    pairing_url: str = Field(..., description="Universal deep-link or webhook handshake target")
    qr_matrix_base64: str = Field(..., description="Data URL representation of the dynamic QR code")
    expires_in_seconds: int = Field(default=300, description="Session TTL in seconds")


class PairingSessionResponse(BaseModel):
    """Comprehensive visual pairing session detail."""

    session_id: str = Field(..., description="Unique pairing session identifier")
    platform: ChannelPlatform = Field(..., description="Target external channel platform")
    status: PairingStatus = Field(..., description="Current status of the pairing flow")
    qr_code: PairingQRCode | None = Field(
        default=None,
        description="Dynamic QR code payload if status is pending or scanned",
    )
    bound_token_masked: str | None = Field(
        default=None,
        description="Masked authentication token once authenticated",
    )
    user_identity: str | None = Field(
        default=None,
        description="Scanned user or bot identity handle",
    )
    created_at_epoch_ms: int = Field(..., description="Session creation epoch in milliseconds")
    error_message: str | None = Field(default=None, description="Detailed error description if failed")


class PairingConfirmRequest(BaseModel):
    """Request to confirm or simulate scan callback."""

    auth_token: str = Field(..., min_length=4, description="Exchanged or scanned authentication token")
    user_identity: str | None = Field(
        default=None,
        description="Optional scanned user/bot identity",
    )


class PairingConfirmResponse(BaseModel):
    """Response returned upon successful handshake confirmation."""

    session_id: str = Field(..., description="Pairing session identifier")
    platform: ChannelPlatform = Field(..., description="Target channel platform")
    status: PairingStatus = Field(..., description="Updated pairing status")
    persisted: bool = Field(default=True, description="Whether token was saved to persistent store")
    message: str = Field(..., description="Human-readable result summary")


class ChannelPingRequest(BaseModel):
    """Request model for one-click ping connectivity probe."""

    platform: ChannelPlatform = Field(..., description="Target external channel")
    target_recipient: str | None = Field(
        default=None,
        description="Target user ID or chat ID. Defaults to paired user if omitted",
    )
    test_message: str = Field(
        default="[Myrm Channel Ping] Model-agnostic connection verified successfully.",
        description="Diagnostic test payload to deliver",
    )


class ChannelPingResponse(BaseModel):
    """Response reporting one-click ping connectivity and latency."""

    platform: ChannelPlatform = Field(..., description="Target external channel")
    success: bool = Field(..., description="Whether ping test succeeded")
    latency_ms: float = Field(..., description="Round-trip or dispatch latency in milliseconds")
    receipt_id: str = Field(..., description="Traceable delivery confirmation ID")
    dispatched_at_epoch_ms: int = Field(..., description="Dispatch timestamp in milliseconds")
    error_detail: str | None = Field(default=None, description="Diagnostic error details if failed")
