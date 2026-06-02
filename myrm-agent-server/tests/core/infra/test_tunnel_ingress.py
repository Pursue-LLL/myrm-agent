import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.infra import ingress
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.infra.tunnel.manager import (
    TunnelError,
    TunnelManager,
    parse_quick_tunnel_url_from_line,
    parse_quick_tunnel_url_from_output,
)

_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"
_CLOUDFLARED_STDERR_FIXTURE = _FIXTURES_DIR / "cloudflared_quick_tunnel_stderr.txt"


@pytest.fixture
def mock_load_personal_settings():
    with patch(
        "app.core.infra.ingress.load_user_config_entry",
        new_callable=AsyncMock,
    ) as mock:
        yield mock


@pytest.fixture
def mock_settings():
    with patch("app.core.infra.ingress.settings") as mock:
        yield mock


def test_parse_quick_tunnel_url_from_cloudflared_stderr_fixture() -> None:
    sample = _CLOUDFLARED_STDERR_FIXTURE.read_text(encoding="utf-8")
    url = parse_quick_tunnel_url_from_output(sample)
    assert url == "https://ample-rice-42.trycloudflare.com"


def test_parse_quick_tunnel_url_from_line_returns_none_when_missing() -> None:
    assert parse_quick_tunnel_url_from_line("INF Starting tunnel") is None


@pytest.mark.asyncio
async def test_start_returns_quickly_when_cloudflared_missing() -> None:
    manager = TunnelManager()
    with (
        patch.object(manager, "_ensure_quick_tunnel_allowed"),
        patch.object(manager, "_resolve_cloudflared_binary", side_effect=TunnelError("cloudflared missing")),
        patch.object(manager, "_reset_tunnel_state_unlocked", new_callable=AsyncMock),
        patch.object(manager, "_sync_ingress_runtime", new_callable=AsyncMock),
    ):
        with pytest.raises(TunnelError, match="cloudflared missing"):
            await asyncio.wait_for(
                manager.start(3000, password_protection_enabled=True),
                timeout=2.0,
            )


@pytest.mark.asyncio
async def test_runtime_tunnel_ingress_priority(mock_settings, mock_load_personal_settings):
    mock_settings.cp_public_ingress_url = ""
    ingress.set_runtime_tunnel_ingress("https://abc.trycloudflare.com")
    mock_load_personal_settings.return_value = {
        "publicIngressBaseUrl": "https://user.example.com",
    }

    url = await get_public_ingress_base_url()

    assert url == "https://abc.trycloudflare.com"
    ingress.set_runtime_tunnel_ingress(None)


@pytest.mark.asyncio
async def test_get_status_cleans_up_dead_process() -> None:
    manager = TunnelManager()
    dead_process = MagicMock()
    dead_process.returncode = 1
    manager._process = dead_process
    manager._url = "https://dead.trycloudflare.com"
    manager._target_port = 3000
    manager._ingress_snapshot = "https://saved.example.com"

    with patch.object(manager, "_sync_ingress_runtime", new_callable=AsyncMock) as mock_sync:
        status = await manager.get_status()

    assert status.running is False
    assert status.url is None
    assert manager._process is None
    mock_sync.assert_awaited_once_with(None)
