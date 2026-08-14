"""Tests for channel instance credential persistence and key normalization.

Covers the credential key mismatch bug (write via ``config_key`` column vs
read/delete via ``id`` column) and camelCase → snake_case normalization for
channel constructors.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.api.channels.router import _CHANNEL_CONFIG_KEYS
from app.channels.core.credentials import (
    camel_to_snake,
    channel_credentials_config_key,
)

# ── channel_credentials_config_key ───────────────────────────────────


class TestChannelCredentialsConfigKey:
    def test_default_channel_uses_registered_mapping(self) -> None:
        assert channel_credentials_config_key("wechat", _CHANNEL_CONFIG_KEYS) == "wechatCredentials"
        assert channel_credentials_config_key("feishu", _CHANNEL_CONFIG_KEYS) == "feishuCredentials"
        assert channel_credentials_config_key("wecom_aibot", _CHANNEL_CONFIG_KEYS) == "wecomAibotCredentials"

    def test_instance_channel_falls_back_to_camel_suffix(self) -> None:
        assert channel_credentials_config_key("wechat_abc123", _CHANNEL_CONFIG_KEYS) == "wechat_abc123Credentials"
        assert channel_credentials_config_key("feishu_xyz", _CHANNEL_CONFIG_KEYS) == "feishu_xyzCredentials"

    def test_unknown_channel_without_mapping(self) -> None:
        assert channel_credentials_config_key("custom_chan") == "custom_chanCredentials"


# ── camel_to_snake ───────────────────────────────────────────────────


class TestCamelToSnake:
    def test_basic_camel_case(self) -> None:
        assert camel_to_snake("appId") == "app_id"
        assert camel_to_snake("appSecret") == "app_secret"
        assert camel_to_snake("botOpenId") == "bot_open_id"

    def test_consecutive_capitals_preserved(self) -> None:
        # The old regex produced base_u_r_l; lookbehind version must not.
        assert camel_to_snake("baseURL") == "base_url"
        assert camel_to_snake("ilinkBotId") == "ilink_bot_id"

    def test_idempotent_for_snake_case(self) -> None:
        assert camel_to_snake("app_id") == "app_id"
        assert camel_to_snake("bot_token") == "bot_token"


# ── _load_instance_credentials ───────────────────────────────────────


@pytest.mark.asyncio
async def test_load_instance_credentials_by_config_key() -> None:
    """Credentials written via ConfigService (config_key column) must be readable."""

    from app.core.channel_bridge.setup import _load_instance_credentials
    from app.database.connection import get_session
    from app.database.models import UserConfig

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        session.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key="feishu_a1b2c3Credentials",
                config_value={"appId": "cli_x", "appSecret": "sec_y", "botOpenId": "ou_z"},
                version="v1",
                last_device_id="test",
                is_encrypted=False,
            )
        )
        await session.commit()

    creds = await _load_instance_credentials("feishu_a1b2c3")
    assert creds is not None
    assert creds["app_id"] == "cli_x"
    assert creds["app_secret"] == "sec_y"
    assert creds["bot_open_id"] == "ou_z"

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


@pytest.mark.asyncio
async def test_load_instance_credentials_missing_returns_none() -> None:
    from app.core.channel_bridge.setup import _load_instance_credentials

    assert await _load_instance_credentials("feishu_no_such") is None


# ── _delete_instance_credentials ─────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_instance_credentials_by_config_key() -> None:
    """Delete must target the config_key column, matching the write side."""
    from sqlalchemy import select

    from app.api.channels.instances import _delete_instance_credentials
    from app.database.connection import get_session
    from app.database.models import UserConfig

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        session.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key="wechat_deadbeefCredentials",
                config_value={"botToken": "tok"},
                version="v1",
                last_device_id="test",
                is_encrypted=False,
            )
        )
        await session.commit()

    await _delete_instance_credentials("wechat_deadbeef")

    async with get_session() as session:
        row = (
            await session.execute(
                select(UserConfig).where(UserConfig.config_key == "wechat_deadbeefCredentials")
            )
        ).scalar_one_or_none()
    assert row is None

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


@pytest.mark.asyncio
async def test_delete_default_channel_credentials() -> None:
    """Default wechat channel logout must remove wechatCredentials config_key."""
    from sqlalchemy import select

    from app.api.channels.instances import _delete_instance_credentials
    from app.database.connection import get_session
    from app.database.models import UserConfig

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        session.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key="wechatCredentials",
                config_value={"botToken": "tok"},
                version="v1",
                last_device_id="test",
                is_encrypted=False,
            )
        )
        await session.commit()

    await _delete_instance_credentials("wechat")

    async with get_session() as session:
        row = (
            await session.execute(
                select(UserConfig).where(UserConfig.config_key == "wechatCredentials")
            )
        ).scalar_one_or_none()
    assert row is None

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


# ── create_channel_instance camel→snake normalization ────────────────


@pytest.mark.asyncio
async def test_create_feishu_instance_converts_camel_credentials() -> None:
    """camelCase credentials from the frontend must reach FeishuChannel snake_case."""
    from app.channels.providers.feishu.channel import FeishuChannel
    from app.core.channel_bridge.channel_factory import create_channel_instance

    with (
        patch.object(FeishuChannel, "from_credentials", autospec=True) as mock_from,
        patch("app.core.channel_bridge.channel_factory.get_channel_class_safe", return_value=FeishuChannel),
    ):
        mock_channel = MagicMock()
        mock_from.return_value = mock_channel
        await create_channel_instance(
            channel_type="feishu",
            instance_id="camel01",
            credentials={"appId": "cli_a", "appSecret": "sec_b", "useLark": "false"},
        )

    mock_from.assert_called_once()
    creds = mock_from.call_args[0][0]
    assert creds["app_id"] == "cli_a"
    assert creds["app_secret"] == "sec_b"
    assert creds["use_lark"] == "false"
    assert "appId" not in creds


@pytest.mark.asyncio
async def test_create_wechat_instance_converts_camel_credentials() -> None:
    from app.channels.providers.wechat.ilink_channel import WeChatILinkChannel
    from app.core.channel_bridge.channel_factory import create_channel_instance

    with (
        patch.object(WeChatILinkChannel, "from_credentials", autospec=True) as mock_from,
        patch("app.core.channel_bridge.channel_factory.get_channel_class_safe", return_value=WeChatILinkChannel),
    ):
        mock_channel = MagicMock()
        mock_from.return_value = mock_channel
        await create_channel_instance(
            channel_type="wechat",
            instance_id="camel02",
            credentials={"botToken": "tok", "baseUrl": "http://x"},
        )

    mock_from.assert_called_once()
    creds = mock_from.call_args[0][0]
    assert creds["bot_token"] == "tok"
    assert creds["base_url"] == "http://x"
    assert "botToken" not in creds


@pytest.mark.asyncio
async def test_create_instance_unknown_channel_raises() -> None:
    from app.core.channel_bridge.channel_factory import create_channel_instance

    with pytest.raises(ValueError, match="Unknown channel type"):
        await create_channel_instance(channel_type="no_such_type", instance_id="x")
