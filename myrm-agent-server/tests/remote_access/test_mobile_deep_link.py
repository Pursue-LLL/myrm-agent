"""Mobile status deep link builder tests."""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.remote_access.mobile_deep_link import build_mobile_status_deep_link
from app.remote_access.pairing import parse_pairing_token


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))


def test_build_mobile_status_deep_link_includes_scoped_pair() -> None:
    url = build_mobile_status_deep_link(chat_id="chat-9", base_url="https://abc.trycloudflare.com")
    assert url is not None
    assert url.startswith("https://abc.trycloudflare.com/mobile/status/chat-9?pair=")
    token = url.split("pair=", 1)[1]
    parsed = parse_pairing_token(token)
    assert parsed is not None
    assert parsed["chat_id"] == "chat-9"


def test_build_mobile_status_deep_link_returns_none_without_base() -> None:
    assert build_mobile_status_deep_link(chat_id="chat-1", base_url="") is None
