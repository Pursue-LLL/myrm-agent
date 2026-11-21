from unittest.mock import AsyncMock, patch

import pytest

from app.core.infra.ingress import (
    get_public_ingress_base_url,
    invalidate_public_ingress_cache,
    resolve_public_link_base,
)
from app.remote_access.tunnel_manager import TunnelManager, TunnelState


@pytest.fixture(autouse=True)
def _clear_ingress_cache():
    invalidate_public_ingress_cache()
    yield
    invalidate_public_ingress_cache()


@pytest.fixture(autouse=True)
def tunnel(monkeypatch: pytest.MonkeyPatch) -> TunnelManager:
    """A stopped tunnel manager (no public URL); tests that need a live tunnel set its state."""
    manager = TunnelManager()
    monkeypatch.setattr("app.remote_access.tunnel_manager.get_tunnel_manager", lambda: manager)
    return manager


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


@pytest.mark.asyncio
async def test_get_public_ingress_base_url_from_cp_env(mock_settings, mock_load_personal_settings):
    mock_settings.cp_public_ingress_url = "https://cp.example.com/"

    url = await get_public_ingress_base_url()

    assert url == "https://cp.example.com"
    mock_load_personal_settings.assert_not_called()


@pytest.mark.asyncio
async def test_get_public_ingress_base_url_from_user_config(mock_settings, mock_load_personal_settings):
    mock_settings.cp_public_ingress_url = ""
    mock_load_personal_settings.return_value = {
        "publicIngressBaseUrl": "https://user.example.com/ ",
    }

    url = await get_public_ingress_base_url()

    assert url == "https://user.example.com"
    mock_load_personal_settings.assert_awaited_once_with("personalSettings")


@pytest.mark.asyncio
async def test_get_public_ingress_base_url_empty(mock_settings, mock_load_personal_settings):
    mock_settings.cp_public_ingress_url = None
    mock_load_personal_settings.return_value = {}

    url = await get_public_ingress_base_url()

    assert url == ""


@pytest.mark.asyncio
async def test_get_public_ingress_base_url_ignores_a_saved_value_that_is_not_text(mock_settings, mock_load_personal_settings):
    """A hand-edited setting that is not a string means no ingress, not a crash."""
    mock_settings.cp_public_ingress_url = ""
    mock_load_personal_settings.return_value = {"publicIngressBaseUrl": 8080}

    assert await get_public_ingress_base_url() == ""


@pytest.mark.asyncio
async def test_get_public_ingress_base_url_uses_short_lived_cache(mock_settings, mock_load_personal_settings):
    invalidate_public_ingress_cache()
    mock_settings.cp_public_ingress_url = ""
    mock_load_personal_settings.return_value = {"publicIngressBaseUrl": "https://cached.example.com"}

    first = await get_public_ingress_base_url()
    second = await get_public_ingress_base_url()

    assert first == "https://cached.example.com"
    assert second == "https://cached.example.com"
    mock_load_personal_settings.assert_awaited_once_with("personalSettings")


@pytest.mark.asyncio
async def test_resolve_public_link_base_returns_ingress(mock_settings, mock_load_personal_settings):
    mock_settings.cp_public_ingress_url = "https://share.example.com/"

    base = await resolve_public_link_base()

    assert base == "https://share.example.com"


@pytest.mark.asyncio
async def test_resolve_public_link_base_falls_back_when_empty(mock_settings, mock_load_personal_settings):
    mock_settings.cp_public_ingress_url = None
    mock_load_personal_settings.return_value = {}

    assert await resolve_public_link_base() == ""
    assert await resolve_public_link_base(fallback="http://testserver") == "http://testserver"


@pytest.mark.asyncio
async def test_resolve_public_link_base_falls_back_on_error(mock_settings, mock_load_personal_settings):
    mock_settings.cp_public_ingress_url = None
    mock_load_personal_settings.side_effect = RuntimeError("boom")

    assert await resolve_public_link_base(fallback="http://origin") == "http://origin"


@pytest.mark.asyncio
async def test_resolve_public_link_base_prefers_running_tunnel(tunnel, mock_settings, mock_load_personal_settings):
    """A live tunnel beats a configured ingress, which may be the address of an earlier tunnel run."""
    tunnel._state = TunnelState.RUNNING
    tunnel._public_url = "https://tunnel.example.com/"
    mock_settings.cp_public_ingress_url = "https://old.example.com"

    assert await resolve_public_link_base(fallback="http://origin") == "https://tunnel.example.com"
    mock_load_personal_settings.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "public_url"),
    [(TunnelState.STOPPED, "https://stale.example.com"), (TunnelState.RUNNING, "")],
)
async def test_resolve_public_link_base_ignores_a_tunnel_without_a_live_address(
    tunnel, mock_settings, mock_load_personal_settings, state, public_url
):
    tunnel._state = state
    tunnel._public_url = public_url
    mock_settings.cp_public_ingress_url = "https://cp.example.com"

    assert await resolve_public_link_base() == "https://cp.example.com"
