"""Remote access admission, tunnel, pairing, and tool policy.

[POS]
Package exports for remote access trust zone, pairing, and tunnel helpers.
"""

from app.remote_access.pairing import create_pairing_token, parse_pairing_token
from app.remote_access.tool_policy import merge_remote_security_overlay
from app.remote_access.trust_zone import (
    AdmissionPath,
    TrustZone,
    admission_path_to_trust_zone,
    is_local_trusted_admission,
    is_public_host,
    resolve_admission_path,
)
from app.remote_access.tunnel_manager import TunnelState, TunnelStatus, get_tunnel_manager

__all__ = [
    "AdmissionPath",
    "TrustZone",
    "TunnelState",
    "TunnelStatus",
    "admission_path_to_trust_zone",
    "create_pairing_token",
    "get_tunnel_manager",
    "is_local_trusted_admission",
    "is_public_host",
    "merge_remote_security_overlay",
    "parse_pairing_token",
    "resolve_admission_path",
]
