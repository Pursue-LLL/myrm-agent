"""Pairing token tests."""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.remote_access.pairing import create_pairing_token, parse_pairing_token


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))


def test_pairing_token_roundtrip() -> None:
    token = create_pairing_token(chat_id="chat-123", purpose="mobile_hub")
    parsed = parse_pairing_token(token)
    assert parsed is not None
    assert parsed["chat_id"] == "chat-123"
    assert parsed["purpose"] == "mobile_hub"


def test_pairing_token_rejects_tamper() -> None:
    token = create_pairing_token(purpose="mobile_hub_list")
    body, sig = token.rsplit(".", 1)
    assert parse_pairing_token(f"{body}.{'x' * len(sig)}") is None
