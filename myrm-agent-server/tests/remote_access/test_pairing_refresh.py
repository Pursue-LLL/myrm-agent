from __future__ import annotations

import time

from app.remote_access.pairing import (
    PAIRING_REFRESH_GRACE_SECONDS,
    create_pairing_token,
    parse_pairing_token,
    refresh_pairing_token,
)


def test_refresh_pairing_token_reissues_same_binding() -> None:
    token = create_pairing_token(chat_id="chat-1", purpose="mobile_hub")
    refreshed = refresh_pairing_token(token)
    assert refreshed is not None
    assert refreshed != token
    parsed = parse_pairing_token(refreshed)
    assert parsed is not None
    assert parsed["chat_id"] == "chat-1"
    assert parsed["purpose"] == "mobile_hub"


def test_refresh_pairing_token_rejects_tampered_token() -> None:
    token = create_pairing_token(chat_id="chat-1")
    assert refresh_pairing_token(f"{token}x") is None


def test_refresh_pairing_token_allows_grace_after_expiry(monkeypatch) -> None:
    token = create_pairing_token(chat_id="chat-1")
    parsed = parse_pairing_token(token)
    assert parsed is not None
    monkeypatch.setattr(time, "time", lambda: parsed["exp"] + PAIRING_REFRESH_GRACE_SECONDS - 1)
    assert refresh_pairing_token(token) is not None
