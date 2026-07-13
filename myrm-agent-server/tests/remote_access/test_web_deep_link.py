"""Web chat deep link builder tests.

Covers:
- build_web_chat_url: URL construction + edge cases
- resolve_web_handoff_components: ActionButton generation + graceful degradation
"""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.remote_access.mobile_deep_link import (
    build_web_chat_url,
    resolve_web_handoff_components,
)
from app.remote_access.tunnel_manager import TunnelManager, TunnelState


@pytest.fixture(autouse=True)
def _state_dir(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))


class TestBuildWebChatUrl:
    def test_returns_url_with_chat_id(self) -> None:
        url = build_web_chat_url(chat_id="abc-def-123", base_url="https://example.com")
        assert url == "https://example.com/abc-def-123"

    def test_returns_none_without_base_url(self) -> None:
        assert build_web_chat_url(chat_id="abc", base_url="") is None

    def test_returns_none_without_chat_id(self) -> None:
        assert build_web_chat_url(chat_id="", base_url="https://example.com") is None

    def test_returns_none_with_both_empty(self) -> None:
        assert build_web_chat_url(chat_id="", base_url="") is None

    def test_preserves_trailing_path(self) -> None:
        url = build_web_chat_url(chat_id="c-12345", base_url="https://host.com")
        assert url == "https://host.com/c-12345"
        assert not url.endswith("/c-12345/")

    def test_base_url_trailing_slash_not_stripped_by_builder(self) -> None:
        """build_web_chat_url does not strip; upstream resolve_mobile_remote_base_url does."""
        url = build_web_chat_url(chat_id="c-1", base_url="https://host.com/")
        assert url == "https://host.com//c-1"


class TestResolveWebHandoffComponents:
    @pytest.fixture(autouse=True)
    def _patch_tunnel_stopped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Default: tunnel stopped, no public URL."""
        manager = TunnelManager()
        manager._state = TunnelState.STOPPED
        manager._public_url = ""
        monkeypatch.setattr(
            "app.remote_access.mobile_deep_link.get_tunnel_manager",
            lambda: manager,
        )

    async def test_returns_empty_when_no_public_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _no_ingress() -> str:
            return ""

        monkeypatch.setattr(
            "app.core.infra.ingress.get_public_ingress_base_url",
            _no_ingress,
        )
        result = await resolve_web_handoff_components("chat-uuid-1", locale="en")
        assert result == ()

    async def test_returns_action_button_with_tunnel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        manager = TunnelManager()
        manager._state = TunnelState.RUNNING
        manager._public_url = "https://tunnel.example.com"
        monkeypatch.setattr(
            "app.remote_access.mobile_deep_link.get_tunnel_manager",
            lambda: manager,
        )

        async def _no_ingress() -> str:
            return ""

        monkeypatch.setattr(
            "app.core.infra.ingress.get_public_ingress_base_url",
            _no_ingress,
        )

        result = await resolve_web_handoff_components("chat-uuid-1", locale="en")
        assert len(result) == 1
        row = result[0]
        assert len(row) == 1
        btn = row[0]
        assert btn.action_id == "web:continue_chat"
        assert btn.url == "https://tunnel.example.com/chat-uuid-1"
        assert btn.style.value == "default"
        assert btn.label

    async def test_returns_action_button_with_ingress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _ingress() -> str:
            return "https://ingress.example.com"

        monkeypatch.setattr(
            "app.core.infra.ingress.get_public_ingress_base_url",
            _ingress,
        )

        result = await resolve_web_handoff_components("db-uuid-2", locale="zh-CN")
        assert len(result) == 1
        btn = result[0][0]
        assert btn.url == "https://ingress.example.com/db-uuid-2"
        assert btn.action_id == "web:continue_chat"

    async def test_tunnel_trailing_slash_stripped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Tunnel URL with trailing slash is normalized by resolve_mobile_remote_base_url."""
        manager = TunnelManager()
        manager._state = TunnelState.RUNNING
        manager._public_url = "https://tunnel.example.com/"
        monkeypatch.setattr(
            "app.remote_access.mobile_deep_link.get_tunnel_manager",
            lambda: manager,
        )

        async def _no_ingress() -> str:
            return ""

        monkeypatch.setattr(
            "app.core.infra.ingress.get_public_ingress_base_url",
            _no_ingress,
        )

        result = await resolve_web_handoff_components("uuid-3", locale="en")
        assert len(result) == 1
        assert result[0][0].url == "https://tunnel.example.com/uuid-3"

    async def test_tunnel_preferred_over_ingress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both tunnel and ingress are available, tunnel takes priority."""
        manager = TunnelManager()
        manager._state = TunnelState.RUNNING
        manager._public_url = "https://tunnel.example.com"
        monkeypatch.setattr(
            "app.remote_access.mobile_deep_link.get_tunnel_manager",
            lambda: manager,
        )

        async def _ingress() -> str:
            return "https://ingress.example.com"

        monkeypatch.setattr(
            "app.core.infra.ingress.get_public_ingress_base_url",
            _ingress,
        )

        result = await resolve_web_handoff_components("uuid-4", locale="en")
        assert len(result) == 1
        assert "tunnel.example.com" in result[0][0].url
        assert "ingress.example.com" not in result[0][0].url
