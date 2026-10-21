"""Connect service: external agent connection management.

[POS] External agent connection management — profiles, MCP snippet builder,
connection state, verification and doctor checks for external agent plugins.
"""

from app.services.connect.profiles import PROFILES, ConnectionProfile
from app.services.connect.service import (
    ConfigSnippet,
    ConnectorState,
    ConnectorStatus,
    ConnectService,
    DoctorResult,
    VerifiedConnectToken,
    get_connect_service,
)

__all__ = [
    "PROFILES",
    "ConfigSnippet",
    "ConnectService",
    "ConnectionProfile",
    "ConnectorState",
    "ConnectorStatus",
    "DoctorResult",
    "VerifiedConnectToken",
    "get_connect_service",
]
