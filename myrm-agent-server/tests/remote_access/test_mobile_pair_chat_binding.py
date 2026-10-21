"""Scoped pair token chat_id binding enforcement tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.security.auth.identity import resolve_identity
from app.remote_access.mobile_gate import PAIR_TOKEN_HEADER, require_mobile_pair_chat_access
from app.remote_access.pairing import MOBILE_HUB_CONTROL_PURPOSE, create_pairing_token


def test_resolve_identity_sets_pair_bound_chat_id() -> None:
    token = create_pairing_token(chat_id="chat-a", purpose=MOBILE_HUB_CONTROL_PURPOSE)
    identity = resolve_identity(
        path="/api/v1/agents/chat/chat-a/attach",
        method="GET",
        headers={PAIR_TOKEN_HEADER: token, "Host": "abc.trycloudflare.com"},
        client_ip="127.0.0.1",
        admission_path="public_ingress",
        trust_zone="remote_exposed",
        local_trusted=False,
    )
    assert identity.auth_source == "pair_token"
    assert identity.pair_bound_chat_id == "chat-a"


def test_require_mobile_pair_chat_access_rejects_other_chat() -> None:
    request = MagicMock()
    request.state.auth_source = "pair_token"
    request.state.pair_bound_chat_id = "chat-a"

    with pytest.raises(HTTPException) as exc_info:
        require_mobile_pair_chat_access(request, "chat-b")

    assert exc_info.value.status_code == 401


def test_require_mobile_pair_chat_access_allows_matching_chat() -> None:
    request = MagicMock()
    request.state.auth_source = "pair_token"
    request.state.pair_bound_chat_id = "chat-a"

    require_mobile_pair_chat_access(request, "chat-a")


def test_require_mobile_pair_chat_access_skips_webui_session() -> None:
    request = MagicMock()
    request.state.auth_source = "webui_session"

    require_mobile_pair_chat_access(request, "chat-b")
