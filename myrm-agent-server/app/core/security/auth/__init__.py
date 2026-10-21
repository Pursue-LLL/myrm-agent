"""Authentication primitives (identity, public paths, session helpers, control plane guard).

[INPUT]
- .control_plane_guard::CP_TOKEN_HEADER_DIRECT (POS: Direct header)
- .control_plane_guard::CP_TOKEN_HEADER_TELEMETRY (POS: Telemetry header)
- .control_plane_guard::extract_provided_cp_token (POS: Extract helper)
- .control_plane_guard::get_expected_control_plane_token (POS: Get expected token)
- .control_plane_guard::verify_control_plane_token (POS: Verification dependency)
- .control_plane_guard::verify_internal_origin (POS: Origin validator)

[OUTPUT]
- CP_TOKEN_HEADER_DIRECT, CP_TOKEN_HEADER_TELEMETRY, extract_provided_cp_token, get_expected_control_plane_token, verify_control_plane_token, verify_internal_origin

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
