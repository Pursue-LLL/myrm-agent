from unittest.mock import AsyncMock, patch

import pytest

from app.core.infra.ingress import get_public_ingress_base_url, invalidate_public_ingress_cache


@pytest.fixture(autouse=True)
def _clear_ingress_cache():
    invalidate_public_ingress_cache()
    yield
    invalidate_public_ingress_cache()


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
async def test_get_public_ingress_base_url_uses_short_lived_cache(mock_settings, mock_load_personal_settings):
    invalidate_public_ingress_cache()
    mock_settings.cp_public_ingress_url = ""
    mock_load_personal_settings.return_value = {"publicIngressBaseUrl": "https://cached.example.com"}

    first = await get_public_ingress_base_url()
    second = await get_public_ingress_base_url()

    assert first == "https://cached.example.com"
    assert second == "https://cached.example.com"
    mock_load_personal_settings.assert_awaited_once_with("personalSettings")
