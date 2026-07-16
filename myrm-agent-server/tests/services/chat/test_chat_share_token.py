"""Tests for chat share HMAC tokens."""

import time
from unittest.mock import patch

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


def test_share_token_rejects_tampered_signature() -> None:
    token, _ = create_chat_share_token("chat-1")
    tampered = token[:-2] + "xx"
    assert parse_chat_share_token(tampered) is None


def test_share_token_rejects_expired() -> None:
    token, _ = create_chat_share_token("chat-1", ttl_seconds=60)
    future = int(time.time()) + 120
    with patch("app.services.chat.share_token.time.time", return_value=future):
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
