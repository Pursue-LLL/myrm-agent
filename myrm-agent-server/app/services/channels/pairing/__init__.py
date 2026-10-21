"""Channel Pairing and Handshake Package.

[INPUT]
- services.channels.pairing.pairing_types
- services.channels.pairing.channel_handshake_service

[OUTPUT]
- ChannelPlatform, PairingStatus, PairingSessionCreateRequest, PairingSessionResponse,
  PairingQRCode, PairingConfirmRequest, PairingConfirmResponse, ChannelPingRequest,
  ChannelPingResponse, ChannelHandshakeService, channel_handshake_service

[POS]
Package facade for model-agnostic visual channel token binding and pairing wizard.
"""

from __future__ import annotations

from app.services.channels.pairing.channel_handshake_service import (
    ChannelHandshakeService,
    channel_handshake_service,
)
from app.services.channels.pairing.pairing_types import (
    ChannelPingRequest,
    ChannelPingResponse,
    ChannelPlatform,
    PairingConfirmRequest,
    PairingConfirmResponse,
    PairingQRCode,
    PairingSessionCreateRequest,
    PairingSessionResponse,
    PairingStatus,
)

__all__ = [
    "ChannelHandshakeService",
    "ChannelPingRequest",
    "ChannelPingResponse",
    "ChannelPlatform",
    "PairingConfirmRequest",
    "PairingConfirmResponse",
    "PairingQRCode",
    "PairingSessionCreateRequest",
    "PairingSessionResponse",
    "PairingStatus",
    "channel_handshake_service",
]
