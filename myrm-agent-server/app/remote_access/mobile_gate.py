"""Mobile remote API access gate: pair token or WebUI session on remote-exposed paths."""

from __future__ import annotations

from collections.abc import Mapping

from app.remote_access.pairing import parse_pairing_token
from app.remote_access.trust_zone import TrustZone

PAIR_TOKEN_HEADER = "X-Pair-Token"


def extract_pair_token(headers: Mapping[str, str], query_string: str = "") -> str | None:
    """Read pairing token from header or `pair` query parameter."""
    for key, value in headers.items():
        if key.lower() == PAIR_TOKEN_HEADER.lower():
            stripped = value.strip()
            if stripped:
                return stripped
    if query_string:
        from urllib.parse import parse_qs

        parsed = parse_qs(query_string.lstrip("?"))
        pair_values = parsed.get("pair")
        if pair_values and pair_values[0].strip():
            return pair_values[0].strip()
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


_CHAT_ID_PATH_PREFIXES = (
    "/api/v1/agents/chat/",
    "/api/v1/agents/chats/",
    "/api/v1/agents/agent/",
    "/api/v1/chats/",
)


def _chat_id_from_mobile_path(path: str) -> str | None:
    """Extract chat id segment from mobile-gated API paths, if present."""
    for prefix in _CHAT_ID_PATH_PREFIXES:
        if path.startswith(prefix):
            segment = path[len(prefix) :].split("/", 1)[0]
            if segment:
                return segment
    return None


def pair_token_authorizes_path(token: str | None, path: str) -> bool:
    """Validate pair token signature/expiry and optional chat_id binding for ``path``."""
    parsed = parse_pairing_token(token)
    if parsed is None:
        return False
    bound_chat_id = parsed.get("chat_id")
    if bound_chat_id is None:
        return True
    path_chat_id = _chat_id_from_mobile_path(path)
    if path_chat_id is None:
        return False
    return path_chat_id == bound_chat_id


def pair_token_grants_access(token: str | None) -> bool:
    return parse_pairing_token(token) is not None


def requires_mobile_remote_gate(*, trust_zone: str | None, path: str) -> bool:
    return trust_zone == TrustZone.REMOTE_EXPOSED.value and is_mobile_remote_api_path(path)


__all__ = [
    "PAIR_TOKEN_HEADER",
    "extract_pair_token",
    "is_mobile_remote_api_path",
    "pair_token_authorizes_path",
    "pair_token_grants_access",
    "requires_mobile_remote_gate",
]
