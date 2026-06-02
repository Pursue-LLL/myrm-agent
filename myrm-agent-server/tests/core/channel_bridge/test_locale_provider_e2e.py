"""Real E2E: personalSettings.locale → UserConfigLocaleProvider → channel i18n text.

No mocks on config load or locale resolution — uses live DB + config API.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.channels.i18n import get_text
from app.channels.types import InboundMessage
from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
from app.core.channel_bridge.locale_provider import UserConfigLocaleProvider
from app.database.connection import get_session
from app.database.models import ConfigAuditLog, UserConfig
from app.main import app

client = TestClient(app, root_path="", headers={"X-Forwarded-For": "127.0.0.1"})


@pytest.fixture(autouse=True)
def _patch_loopback():
    """Ensure TestClient requests are treated as loopback for auth."""
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield


@pytest.fixture(autouse=True)
async def cleanup_db(init_test_database: None) -> None:
    from app.database.connection import init_database

    await init_database()
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    invalidate_user_configs_cache()
    yield
    async with get_session() as session:
        await session.execute(ConfigAuditLog.__table__.delete())
        await session.execute(UserConfig.__table__.delete())
        await session.commit()
    invalidate_user_configs_cache()


def _set_personal_locale(locale: str) -> None:
    response = client.put(
        "/api/v1/config/personalSettings",
        json={
            "value": {
                "locale": locale,
                "fetchRawWebpage": False,
            },
            "device_id": "e2e_channel_locale",
        },
    )
    assert response.status_code == 200, response.text
    invalidate_user_configs_cache()


@pytest.mark.asyncio
async def test_locale_provider_reads_zh_cn_from_config() -> None:
    _set_personal_locale("zh-CN")
    provider = UserConfigLocaleProvider()
    msg = InboundMessage(channel="telegram", sender_id="u1", content="/help")
    assert await provider.resolve_locale(msg) == "zh-CN"


@pytest.mark.asyncio
async def test_locale_provider_reads_en_from_config() -> None:
    _set_personal_locale("en")
    provider = UserConfigLocaleProvider()
    msg = InboundMessage(channel="telegram", sender_id="u1", content="/help")
    assert await provider.resolve_locale(msg) == "en"


@pytest.mark.asyncio
async def test_config_locale_produces_zh_channel_help_text() -> None:
    """Full chain: GUI config locale → provider → localized slash-command catalog."""
    _set_personal_locale("zh-CN")
    provider = UserConfigLocaleProvider()
    base = InboundMessage(channel="telegram", sender_id="u1", content="/help")
    locale = await provider.resolve_locale(base)
    enriched = InboundMessage(
        channel=base.channel,
        sender_id=base.sender_id,
        content=base.content,
        metadata={"locale": locale},
    )
    assert "可用命令" in get_text(enriched, "help_header")


@pytest.mark.asyncio
async def test_config_locale_produces_en_channel_help_text() -> None:
    _set_personal_locale("en-US")
    provider = UserConfigLocaleProvider()
    base = InboundMessage(channel="telegram", sender_id="u1", content="/help")
    locale = await provider.resolve_locale(base)
    enriched = InboundMessage(
        channel=base.channel,
        sender_id=base.sender_id,
        content=base.content,
        metadata={"locale": locale},
    )
    help_text = get_text(enriched, "help_header")
    assert "command" in help_text.lower()
