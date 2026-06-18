"""Mobile remote API access gate: pair token or WebUI session on remote-exposed paths.

[POS]
Path-scoped pair token and session authorization for mobile hub APIs.
"""

from __future__ import annotations

from collections.abc import Mapping

from app.remote_access.pairing import (
    MOBILE_HUB_CONTROL_PURPOSE,
    MOBILE_HUB_LIST_PURPOSE,
    parse_pairing_token,
)
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


def resolve_request_pair_token(request: object, pair_query: str | None = None) -> str | None:
    """Resolve pair token from E2EE decrypt, query param, or plain header."""
    state = getattr(request, "state", None)
    if state is not None:
        override = getattr(state, "e2ee_pair_token", None)
        if isinstance(override, str) and override.strip():
            return override.strip()
    if isinstance(pair_query, str) and pair_query.strip():
        return pair_query.strip()
    url = getattr(request, "url", None)
    query_string = str(getattr(url, "query", "")) if url is not None else ""
    headers = getattr(request, "headers", {})
    return extract_pair_token(headers, query_string)


def is_mobile_remote_api_path(path: str) -> bool:
    """Return True when the path is used by the mobile Hub / Status control surface."""
    if path.startswith("/api/v1/remote-access/"):
        if path.startswith("/api/v1/remote-access/pairing-token"):
            return False
        if path.startswith("/api/v1/remote-access/e2ee/"):
            return False
        return True
    if path.startswith("/api/v1/agents/chat/") and path.endswith("/attach"):
        return True
    if path == "/api/v1/agents/agent-stream":
        return True
    if path.startswith("/api/v1/agents/chats/") and (
        path.endswith("/steer") or path.endswith("/cancel")
    ):
        return True
    if path.startswith("/api/v1/chats/"):
        return True
    return False


def is_mobile_remote_ws_path(path: str) -> bool:
    """Return True for WebSocket endpoints used by the mobile remote control surface."""
    return path.startswith("/ws/stt/")


def is_mobile_remote_control_path(path: str) -> bool:
    """HTTP or WS paths that accept mobile pair tokens on remote-exposed admission."""
    return is_mobile_remote_api_path(path) or is_mobile_remote_ws_path(path)


_CHAT_ID_PATH_PREFIXES = (
    "/api/v1/agents/chat/",
    "/api/v1/agents/chats/",
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


MOBILE_SESSIONS_PATH = "/api/v1/remote-access/mobile/sessions"
MOBILE_PAIRING_ISSUE_PATH = "/api/v1/remote-access/pairing-token"
MOBILE_PAIRING_REFRESH_PATH = "/api/v1/remote-access/pairing-token/refresh"
E2EE_PUBLIC_KEY_PATH = "/api/v1/remote-access/e2ee/public-key"
E2EE_HANDSHAKE_PATH = "/api/v1/remote-access/e2ee/handshake"
_AGENT_STREAM_PATH = "/api/v1/agents/agent-stream"


def is_e2ee_bootstrap_path(path: str) -> bool:
    """E2EE key fetch and handshake are allowed before pair tokens on remote-exposed paths."""
    return path in (E2EE_PUBLIC_KEY_PATH, E2EE_HANDSHAKE_PATH)


def is_mobile_remote_pairing_path(path: str) -> bool:
    """Pairing issue/refresh endpoints used by the mobile Hub token lifecycle."""
    return path in (MOBILE_PAIRING_ISSUE_PATH, MOBILE_PAIRING_REFRESH_PATH)


def _purpose_allows_path(purpose: str, path: str) -> bool:
    if purpose == MOBILE_HUB_LIST_PURPOSE:
        return path in (
            MOBILE_SESSIONS_PATH,
            MOBILE_PAIRING_ISSUE_PATH,
            MOBILE_PAIRING_REFRESH_PATH,
        )
    if purpose != MOBILE_HUB_CONTROL_PURPOSE:
        return False
    if path == MOBILE_SESSIONS_PATH:
        return False
    if is_mobile_remote_pairing_path(path):
        return True
    if not is_mobile_remote_control_path(path):
        return False
    return True


def pair_token_authorizes_path(token: str | None, path: str) -> bool:
    """Validate pair token signature/expiry, purpose, and chat_id binding for ``path``."""
    parsed = parse_pairing_token(token)
    if parsed is None:
        return False
    purpose = parsed.get("purpose")
    if not isinstance(purpose, str) or not _purpose_allows_path(purpose, path):
        return False
    bound_chat_id = parsed.get("chat_id")
    if purpose == MOBILE_HUB_LIST_PURPOSE:
        return bound_chat_id is None
    if not isinstance(bound_chat_id, str):
        return False
    if is_mobile_remote_pairing_path(path):
        return True
    path_chat_id = _chat_id_from_mobile_path(path)
    if path_chat_id is None:
        return is_mobile_remote_ws_path(path) or path == _AGENT_STREAM_PATH
    return path_chat_id == bound_chat_id


def pair_token_grants_access(token: str | None) -> bool:
    return parse_pairing_token(token) is not None


def requires_mobile_remote_gate(*, trust_zone: str | None, path: str) -> bool:
    return trust_zone == TrustZone.REMOTE_EXPOSED.value and is_mobile_remote_api_path(path)


def require_mobile_pair_chat_access(request: object, chat_id: str | None) -> None:
    """Reject pair-token requests when ``chat_id`` does not match the scoped token binding."""
    from fastapi import HTTPException

    state = getattr(request, "state", None)
    if state is None:
        return
    if getattr(state, "auth_source", None) != "pair_token":
        return
    bound = getattr(state, "pair_bound_chat_id", None)
    if not isinstance(bound, str):
        raise HTTPException(status_code=401, detail="Scoped pair token required")
    if not chat_id or bound != chat_id:
        raise HTTPException(status_code=401, detail="Pair token not authorized for this chat")


__all__ = [
    "E2EE_HANDSHAKE_PATH",
    "E2EE_PUBLIC_KEY_PATH",
    "MOBILE_PAIRING_ISSUE_PATH",
    "MOBILE_PAIRING_REFRESH_PATH",
    "MOBILE_SESSIONS_PATH",
    "PAIR_TOKEN_HEADER",
    "extract_pair_token",
    "resolve_request_pair_token",
    "is_e2ee_bootstrap_path",
    "is_mobile_remote_api_path",
    "is_mobile_remote_control_path",
    "is_mobile_remote_pairing_path",
    "is_mobile_remote_ws_path",
    "pair_token_authorizes_path",
    "pair_token_grants_access",
    "require_mobile_pair_chat_access",
    "requires_mobile_remote_gate",
]
