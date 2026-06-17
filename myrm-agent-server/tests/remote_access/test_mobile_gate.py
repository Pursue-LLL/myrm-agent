"""Mobile remote gate tests."""

from __future__ import annotations

from app.remote_access.mobile_gate import (
    PAIR_TOKEN_HEADER,
    extract_pair_token,
    is_mobile_remote_api_path,
    is_mobile_remote_control_path,
    is_mobile_remote_ws_path,
    pair_token_authorizes_path,
    pair_token_grants_access,
    requires_mobile_remote_gate,
)
from app.remote_access.pairing import (
    MOBILE_HUB_CONTROL_PURPOSE,
    MOBILE_HUB_LIST_PURPOSE,
    create_pairing_token,
)


def test_is_mobile_remote_api_path_attach() -> None:
    assert is_mobile_remote_api_path("/api/v1/agents/chat/abc/attach")


def test_is_mobile_remote_ws_path_stt() -> None:
    assert is_mobile_remote_ws_path("/ws/stt/stream")
    assert is_mobile_remote_control_path("/ws/stt/stream")


def test_is_mobile_remote_api_path_excludes_pairing_issue() -> None:
    assert not is_mobile_remote_api_path("/api/v1/remote-access/pairing-token")


def test_requires_mobile_remote_gate_only_on_remote_exposed() -> None:
    assert requires_mobile_remote_gate(
        trust_zone="remote_exposed",
        path="/api/v1/agents/chat/abc/attach",
    )
    assert not requires_mobile_remote_gate(
        trust_zone="local_trusted",
        path="/api/v1/agents/chat/abc/attach",
    )


def test_extract_pair_token_from_header() -> None:
    token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    headers = {PAIR_TOKEN_HEADER: token}
    assert extract_pair_token(headers) == token


def test_pair_token_grants_access() -> None:
    assert pair_token_grants_access(create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE))
    assert not pair_token_grants_access("invalid.token")


def test_hub_list_token_only_authorizes_hub_paths() -> None:
    token = create_pairing_token(purpose=MOBILE_HUB_LIST_PURPOSE)
    sessions_path = "/api/v1/remote-access/mobile/sessions"
    assert pair_token_authorizes_path(token, sessions_path)
    assert pair_token_authorizes_path(token, "/api/v1/remote-access/pairing-token")
    assert pair_token_authorizes_path(token, "/api/v1/remote-access/pairing-token/refresh")
    assert not pair_token_authorizes_path(token, "/api/v1/agents/chat/chat-a/attach")
    assert not pair_token_authorizes_path(token, "/api/v1/agents/agent-stream")
    assert not pair_token_authorizes_path(token, "/ws/stt/stream")


def test_scoped_control_token_authorizes_refresh_path() -> None:
    token = create_pairing_token(chat_id="chat-a", purpose=MOBILE_HUB_CONTROL_PURPOSE)
    assert pair_token_authorizes_path(token, "/api/v1/remote-access/pairing-token/refresh")


def test_scoped_control_token_authorizes_matching_paths() -> None:
    token = create_pairing_token(chat_id="chat-a", purpose=MOBILE_HUB_CONTROL_PURPOSE)
    assert pair_token_authorizes_path(token, "/api/v1/agents/chat/chat-a/attach")
    assert pair_token_authorizes_path(token, "/api/v1/agents/agent-stream")
    assert pair_token_authorizes_path(token, "/api/v1/agents/chats/chat-a/steer")
    assert pair_token_authorizes_path(token, "/api/v1/agents/chats/chat-a/cancel")
    assert pair_token_authorizes_path(token, "/ws/stt/stream")
    assert not pair_token_authorizes_path(token, "/api/v1/remote-access/mobile/sessions")
    assert not pair_token_authorizes_path(token, "/api/v1/agents/chat/chat-b/attach")
    assert not pair_token_authorizes_path(token, "/api/v1/agents/chats/chat-b/cancel")


def test_scoped_control_token_rejects_message_cancel_path() -> None:
    token = create_pairing_token(chat_id="chat-a", purpose=MOBILE_HUB_CONTROL_PURPOSE)
    assert not pair_token_authorizes_path(token, "/api/v1/agents/agent/msg-1/cancel")


def test_scoped_pair_authorizes_mobile_stt_ws() -> None:
    token = create_pairing_token(chat_id="chat-a", purpose=MOBILE_HUB_CONTROL_PURPOSE)
    assert pair_token_authorizes_path(token, "/ws/stt/stream")
