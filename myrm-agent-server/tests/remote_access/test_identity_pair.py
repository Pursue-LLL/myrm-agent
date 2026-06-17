"""Identity resolution with mobile pair tokens."""

from __future__ import annotations

from app.core.security.auth.identity import resolve_identity
from app.remote_access.mobile_gate import PAIR_TOKEN_HEADER
from app.remote_access.pairing import create_pairing_token


def test_remote_attach_accepts_valid_pair_token() -> None:
    token = create_pairing_token()
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


def test_remote_attach_accepts_valid_pair_query() -> None:
    token = create_pairing_token()
    identity = resolve_identity(
        path="/api/v1/remote-access/mobile/sessions",
        method="GET",
        headers={"Host": "abc.trycloudflare.com"},
        client_ip="127.0.0.1",
        admission_path="public_ingress",
        trust_zone="remote_exposed",
        local_trusted=False,
        query_string=f"pair={token}",
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


def test_remote_attach_rejects_scoped_token_on_other_chat() -> None:
    token = create_pairing_token(chat_id="chat-a")
    identity = resolve_identity(
        path="/api/v1/agents/chat/chat-b/attach",
        method="GET",
        headers={PAIR_TOKEN_HEADER: token, "Host": "abc.trycloudflare.com"},
        client_ip="127.0.0.1",
        admission_path="public_ingress",
        trust_zone="remote_exposed",
        local_trusted=False,
    )
    assert identity.user_id is None


def test_remote_attach_accepts_scoped_token_on_matching_chat() -> None:
    token = create_pairing_token(chat_id="chat-a")
    identity = resolve_identity(
        path="/api/v1/agents/chat/chat-a/attach",
        method="GET",
        headers={PAIR_TOKEN_HEADER: token, "Host": "abc.trycloudflare.com"},
        client_ip="127.0.0.1",
        admission_path="public_ingress",
        trust_zone="remote_exposed",
        local_trusted=False,
    )
    assert identity.user_id == "local-user"
    assert identity.auth_source == "pair_token"
