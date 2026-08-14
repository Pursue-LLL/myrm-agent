"""Tests for chat share HMAC tokens (including password gate)."""

import time
from unittest.mock import patch

from app.core.security.share_hmac import is_password_protected
from app.services.chat.share_token import (
    create_chat_share_token,
    parse_chat_share_token,
)


def test_share_token_round_trip() -> None:
    token, exp = create_chat_share_token("chat-abc-123", ttl_seconds=3600)
    claims = parse_chat_share_token(token)
    assert claims is not None
    assert claims.chat_id == "chat-abc-123"
    assert claims.exp == exp
    assert claims.password_protected is False


def test_share_token_rejects_tampered_signature() -> None:
    token, _ = create_chat_share_token("chat-1")
    tampered = token[:-2] + "xx"
    assert parse_chat_share_token(tampered) is None


def test_share_token_rejects_expired() -> None:
    token, _ = create_chat_share_token("chat-1", ttl_seconds=60)
    future = int(time.time()) + 120
    with patch("app.core.security.share_hmac.time.time", return_value=future):
        assert parse_chat_share_token(token) is None


def test_share_token_rejects_empty_or_malformed() -> None:
    assert parse_chat_share_token("") is None
    assert parse_chat_share_token("not-a-valid-token") is None
    assert parse_chat_share_token("abc.def.ghi") is None


def test_share_token_ttl_clamping() -> None:
    _, exp = create_chat_share_token("chat-1", ttl_seconds=10)
    now = int(time.time())
    assert exp >= now + 60

    _, exp_max = create_chat_share_token("chat-1", ttl_seconds=999999999)
    assert exp_max <= now + 30 * 24 * 3600 + 2


def test_share_token_different_chats_produce_different_tokens() -> None:
    t1, _ = create_chat_share_token("chat-a")
    t2, _ = create_chat_share_token("chat-b")
    assert t1 != t2


# ── Password gate tests ──────────────────────────────────────────


def test_password_token_round_trip() -> None:
    token, exp = create_chat_share_token("chat-pw", ttl_seconds=3600, password="abc")
    assert is_password_protected(token) is True
    assert parse_chat_share_token(token) is None
    claims = parse_chat_share_token(token, password="abc")
    assert claims is not None
    assert claims.chat_id == "chat-pw"
    assert claims.password_protected is True
    assert claims.exp == exp


def test_password_token_rejects_wrong_password() -> None:
    token, _ = create_chat_share_token("chat-pw", password="right")
    assert parse_chat_share_token(token, password="wrong") is None


def test_non_password_token_not_protected() -> None:
    token, _ = create_chat_share_token("chat-1")
    assert is_password_protected(token) is False


def test_share_token_rejects_non_string_chat_id() -> None:
    """A validly-signed token whose cid claim is not a string must be rejected."""
    import time

    from app.core.security.share_hmac import sign_share_token

    token = sign_share_token(
        {"cid": 12345},
        salt="chat-share",
        exp=int(time.time()) + 3600,
    )
    assert parse_chat_share_token(token) is None
