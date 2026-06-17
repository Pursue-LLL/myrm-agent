"""Mobile remote gate tests."""

from __future__ import annotations

from app.remote_access.mobile_gate import (
    PAIR_TOKEN_HEADER,
    extract_pair_token,
    is_mobile_remote_api_path,
    pair_token_grants_access,
    requires_mobile_remote_gate,
)
from app.remote_access.pairing import create_pairing_token


def test_is_mobile_remote_api_path_attach() -> None:
    assert is_mobile_remote_api_path("/api/v1/agents/chat/abc/attach")


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
    token = create_pairing_token()
    headers = {PAIR_TOKEN_HEADER: token}
    assert extract_pair_token(headers) == token


def test_pair_token_grants_access() -> None:
    assert pair_token_grants_access(create_pairing_token())
    assert not pair_token_grants_access("invalid.token")
