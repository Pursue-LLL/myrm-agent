"""Identity resolution with mobile pair tokens."""

from __future__ import annotations

from app.core.security.auth.identity import resolve_identity
from app.remote_access.mobile_gate import PAIR_TOKEN_HEADER
from app.remote_access.pairing import MOBILE_HUB_CONTROL_PURPOSE, MOBILE_HUB_LIST_PURPOSE, create_pairing_token


def test_remote_attach_accepts_valid_pair_token() -> None:
    token = create_pairing_token(chat_id="chat-123", purpose=MOBILE_HUB_CONTROL_PURPOSE)
    identity = resolve_identity(
        path="/api/v1/agents/chat/chat-123/attach",
        method="GET",
        headers={PAIR_TOKEN_HEADER: token, "Host": "abc.trycloudflare.com"},
        client_ip="127.0.0.1",
        admission_path="public_ingress",
        trust_zone="remote_exposed",
        local_trusted=False,
    )
    assert identity.user_id == "local-user"
    assert identity.auth_source == "pair_token"


def test_remote_attach_rejects_missing_pair_and_session() -> None:
    identity = resolve_identity(
        path="/api/v1/agents/chat/chat-123/attach",
        method="GET",
        headers={"Host": "abc.trycloudflare.com"},
        client_ip="127.0.0.1",
        admission_path="public_ingress",
        trust_zone="remote_exposed",
        local_trusted=False,
    )
    assert identity.user_id is None


def test_remote_stt_ws_accepts_scoped_pair_query() -> None:
    from app.core.security.auth.identity import resolve_identity_from_ws_scope

    token = create_pairing_token(chat_id="chat-a", purpose=MOBILE_HUB_CONTROL_PURPOSE)
    scope = {
        "type": "websocket",
        "path": "/ws/stt/stream",
        "query_string": f"pair={token}".encode("latin-1"),
        "headers": [(b"host", b"abc.trycloudflare.com")],
        "client": ("127.0.0.1", 54321),
    }
    identity = resolve_identity_from_ws_scope(scope)
    assert identity.user_id == "local-user"
    assert identity.auth_source == "pair_token"
