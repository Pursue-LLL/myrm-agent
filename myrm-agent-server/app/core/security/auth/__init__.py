"""Authentication primitives (identity, public paths, session helpers, control plane guard).

[INPUT]
- app.core.security.auth.control_plane_guard (POS: control plane guard tokens and verification helpers)

[OUTPUT]
- exports CP_TOKEN_HEADER_DIRECT, CP_TOKEN_HEADER_TELEMETRY, verify_control_plane_token, etc.

[POS]
SSOT facade re-exporting authentication helpers and tokens.
"""

from app.core.security.auth.control_plane_guard import (
    CP_TOKEN_HEADER_DIRECT,
    CP_TOKEN_HEADER_TELEMETRY,
    extract_provided_cp_token,
    get_expected_control_plane_token,
    verify_control_plane_token,
    verify_internal_origin,
)

__all__ = [
    "CP_TOKEN_HEADER_DIRECT",
    "CP_TOKEN_HEADER_TELEMETRY",
    "extract_provided_cp_token",
    "get_expected_control_plane_token",
    "verify_control_plane_token",
    "verify_internal_origin",
]

