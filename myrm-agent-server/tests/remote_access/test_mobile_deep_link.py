"""Mobile status deep link builder tests."""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.remote_access.mobile_deep_link import (
    build_mobile_status_deep_link,
    resolve_mobile_remote_base_url,
)
from app.remote_access.pairing import parse_pairing_token
from app.remote_access.tunnel_manager import TunnelManager, TunnelState


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


def test_resolve_mobile_remote_base_url_prefers_running_tunnel(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = TunnelManager()
    manager._state = TunnelState.RUNNING
    manager._public_url = "https://tunnel.example.com"
    monkeypatch.setattr("app.remote_access.mobile_deep_link.get_tunnel_manager", lambda: manager)
    assert resolve_mobile_remote_base_url(public_ingress_base_url="https://ingress.example.com") == (
        "https://tunnel.example.com"
    )


def test_build_mobile_status_deep_link_returns_none_without_base() -> None:
    assert build_mobile_status_deep_link(chat_id="chat-1", base_url="") is None
