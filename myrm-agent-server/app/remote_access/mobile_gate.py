"""Mobile remote API access gate: pair token or WebUI session on remote-exposed paths."""

from __future__ import annotations

from collections.abc import Mapping

from app.remote_access.pairing import parse_pairing_token
from app.remote_access.trust_zone import TrustZone

PAIR_TOKEN_HEADER = "X-Pair-Token"


def extract_pair_token(headers: Mapping[str, str]) -> str | None:
    """Read pairing token from the mobile remote header."""
    for key, value in headers.items():
        if key.lower() == PAIR_TOKEN_HEADER.lower():
            stripped = value.strip()
            return stripped or None
    return None


def is_mobile_remote_api_path(path: str) -> bool:
    """Return True when the path is used by the mobile Hub / Status control surface."""
    if path.startswith("/api/v1/remote-access/"):
        if path.startswith("/api/v1/remote-access/pairing-token"):
            return False
        return True
    if path.startswith("/api/v1/agents/chat/") and path.endswith("/attach"):
        return True
    if path == "/api/v1/agents/agent-stream":
        return True
    if path.startswith("/api/v1/agents/chats/") and path.endswith("/steer"):
        return True
    if path.startswith("/api/v1/agents/agent/") and path.endswith("/cancel"):
        return True
    if path.startswith("/api/v1/chats/"):
        return True
    return False


def pair_token_grants_access(token: str | None) -> bool:
    return parse_pairing_token(token) is not None


def requires_mobile_remote_gate(*, trust_zone: str | None, path: str) -> bool:
    return trust_zone == TrustZone.REMOTE_EXPOSED.value and is_mobile_remote_api_path(path)


__all__ = [
    "PAIR_TOKEN_HEADER",
    "extract_pair_token",
    "is_mobile_remote_api_path",
    "pair_token_grants_access",
    "requires_mobile_remote_gate",
]
