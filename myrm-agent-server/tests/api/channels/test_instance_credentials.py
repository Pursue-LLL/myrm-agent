"""Tests for channel instance credential persistence and key normalization.

Covers the credential key mismatch bug (write via ``config_key`` column vs
read/delete via ``id`` column) and camelCase → snake_case normalization for
channel constructors.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

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
                config_value={"appId": "cli_x", "appSecret": "sec_y", "botOpenId": "ou_z", "useLark": False},
                version="v1",
                last_device_id="test",
                is_encrypted=False,
            )
        )
        await session.commit()

    creds = await _load_instance_credentials("feishu_a1b2c3")
    assert creds is not None
    assert creds["appId"] == "cli_x"
    assert creds["appSecret"] == "sec_y"
    assert creds["botOpenId"] == "ou_z"
    # Boolean credentials are flattened to lowercase strings on load, keeping
    # them consistent with the values submitted by the frontend.
    assert creds["useLark"] == "false"

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
            await session.execute(select(UserConfig).where(UserConfig.config_key == "wechat_deadbeefCredentials"))
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
        row = (await session.execute(select(UserConfig).where(UserConfig.config_key == "wechatCredentials"))).scalar_one_or_none()
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


@pytest.mark.asyncio
async def test_create_dingtalk_instance_maps_spec_db_keys() -> None:
    """Spec db_keys that are NOT camel_to_snake(param) (e.g. clientId -> app_key)
    must still map to constructor params via the channel credential spec."""
    from app.channels.providers.dingtalk.channel import DingTalkChannel
    from app.core.channel_bridge.channel_factory import create_channel_instance

    with (
        patch.object(DingTalkChannel, "from_credentials", autospec=True) as mock_from,
        patch("app.core.channel_bridge.channel_factory.get_channel_class_safe", return_value=DingTalkChannel),
    ):
        mock_channel = MagicMock()
        mock_from.return_value = mock_channel
        await create_channel_instance(
            channel_type="dingtalk",
            instance_id="camel03",
            credentials={"clientId": "cli_a", "clientSecret": "sec_b", "robotCode": "robot_c"},
        )

    mock_from.assert_called_once()
    creds = mock_from.call_args[0][0]
    assert creds["app_key"] == "cli_a"
    assert creds["app_secret"] == "sec_b"
    assert creds["robot_code"] == "robot_c"
    assert "client_id" not in creds
    assert "clientId" not in creds


@pytest.mark.asyncio
async def test_create_instance_without_spec_falls_back_to_camel_to_snake() -> None:
    """Channels without a credential spec keep camelCase → snake_case fallback."""
    from app.channels.providers.webhook import WebhookChannel
    from app.core.channel_bridge.channel_factory import create_channel_instance

    assert WebhookChannel.credential_spec is None

    with (
        patch.object(WebhookChannel, "from_credentials", autospec=True) as mock_from,
        patch("app.core.channel_bridge.channel_factory.get_channel_class_safe", return_value=WebhookChannel),
    ):
        mock_channel = MagicMock()
        mock_from.return_value = mock_channel
        await create_channel_instance(
            channel_type="webhook",
            instance_id="camel04",
            credentials={"sharedSecret": "s3cret"},
        )

    mock_from.assert_called_once()
    creds = mock_from.call_args[0][0]
    assert creds["shared_secret"] == "s3cret"
    assert "sharedSecret" not in creds


# ── create_channel_instance API persists credentials ──────────────────


@pytest.mark.asyncio
async def test_api_create_instance_persists_credentials() -> None:
    """Manually created instance with credentials must persist them to the
    ``{channel_name}Credentials`` config_key so restart recovery works."""
    from sqlalchemy import select

    from app.api.channels.router import channel_credentials_key
    from app.core.channel_bridge.channel_factory import (
        generate_instance_id,
    )
    from app.database.connection import get_session
    from app.database.models import UserConfig

    instance_id = generate_instance_id()
    channel_name = f"feishu_{instance_id}"
    creds = {"appId": "cli_persist", "appSecret": "sec_persist", "useLark": "false"}

    mock_channel = MagicMock()
    mock_channel.name = channel_name
    mock_channel.status = "stopped"
    mock_channel.display_name = "Persist App"

    gateway = MagicMock()
    gateway.add_channel = AsyncMock(return_value=channel_name)

    factory = MagicMock()
    factory.create_channel_instance = AsyncMock(return_value=mock_channel)

    with (
        patch("app.core.channel_bridge.channel_gateway", gateway),
        patch(
            "app.core.channel_bridge.channel_factory.create_channel_instance",
            factory.create_channel_instance,
        ),
        patch(
            "app.core.channel_bridge.channel_factory.generate_instance_id",
            return_value=instance_id,
        ),
        patch(
            "app.core.channel_bridge.channel_factory.load_persisted_instances",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            "app.core.channel_bridge.channel_factory.save_persisted_instances",
            new_callable=AsyncMock,
        ),
    ):
        from app.api.channels.instances import create_channel_instance as api_create

        body = MagicMock()
        body.channel_type = "feishu"
        body.display_name = "Persist App"
        body.credentials = creds

        result = await api_create(body)

    assert result.channel_name == channel_name

    config_key = channel_credentials_key(channel_name)
    assert config_key == f"feishu_{instance_id}Credentials"

    async with get_session() as session:
        row = (await session.execute(select(UserConfig).where(UserConfig.config_key == config_key))).scalar_one_or_none()
    assert row is not None
    assert row.is_encrypted is True
    assert "_cipher" in row.config_value

    from app.services.config.service import ConfigService

    record = await ConfigService().get(config_key)
    assert record is not None
    assert record.value["appId"] == "cli_persist"
    assert record.value["appSecret"] == "sec_persist"

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


# ── credentials endpoint stores encrypted & returns redacted ─────────


@pytest.mark.asyncio
async def test_save_channel_credentials_encrypts_instance_key() -> None:
    """The credentials endpoint must store instance keys encrypted at rest."""
    from sqlalchemy import select

    from app.api.channels.instances import save_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.database.connection import get_session
    from app.database.models import UserConfig

    channel_name = f"feishu_{uuid.uuid4().hex[:8]}"
    creds = {"appId": "cli_endpoint", "appSecret": "sec_endpoint", "useLark": "false"}

    with patch("app.core.channel_bridge.channel_gateway.bus") as mock_bus:
        mock_bus.get_channel.return_value = None
        result = await save_channel_credentials(channel_name, creds)

    assert result["status"] == "saved"

    config_key = channel_credentials_key(channel_name)
    async with get_session() as session:
        row = (
            await session.execute(select(UserConfig).where(UserConfig.config_key == config_key))
        ).scalar_one_or_none()
    assert row is not None
    assert row.is_encrypted is True
    assert "_cipher" in row.config_value

    async with get_session() as session:
        await session.execute(UserConfig.__table__.delete())
        await session.commit()


@pytest.mark.asyncio
async def test_save_channel_credentials_merge_preserves_omitted_fields() -> None:
    """Only submitted fields are overwritten; omitted keys survive the update."""
    from app.api.channels.instances import save_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    channel_name = f"feishu_{uuid.uuid4().hex[:8]}"
    config_key = channel_credentials_key(channel_name)
    await ConfigService().set(
        config_key,
        {"appId": "cli_keep", "appSecret": "old_secret", "botOpenId": "ou_keep", "useLark": "false"},
        device_id="test",
    )

    try:
        with patch("app.core.channel_bridge.channel_gateway.bus") as mock_bus:
            mock_bus.get_channel.return_value = None
            await save_channel_credentials(channel_name, {"appSecret": "new_secret"})

        record = await ConfigService().get(config_key)
        assert record is not None
        assert record.value["appId"] == "cli_keep"
        assert record.value["appSecret"] == "new_secret"
        assert record.value["botOpenId"] == "ou_keep"
        assert record.value["useLark"] == "false"
    finally:
        await ConfigService().delete(config_key)


@pytest.mark.asyncio
async def test_save_channel_credentials_rebuilds_multi_instance() -> None:
    """A registered multi-app instance must be recreated from merged credentials
    with the same instance id (so the channel name and agent bindings survive)."""
    from app.api.channels.instances import save_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    instance_id = uuid.uuid4().hex[:8]
    channel_name = f"feishu_{instance_id}"

    old_channel = MagicMock()
    old_channel.name = channel_name
    old_channel.channel_type = "feishu"
    old_channel.instance_id = instance_id
    old_channel.display_name = "客服机器人"

    new_channel = MagicMock()
    new_channel.name = channel_name

    gateway = MagicMock()
    gateway._resolve_channel_type = MagicMock(return_value="feishu")
    gateway.bus.get_channel = MagicMock(return_value=old_channel)
    gateway.remove_channel = AsyncMock(return_value=True)
    gateway.add_channel = AsyncMock(return_value=channel_name)

    factory = MagicMock()
    factory.create_channel_instance = AsyncMock(return_value=new_channel)

    with (
        patch("app.core.channel_bridge.channel_gateway", gateway),
        patch(
            "app.core.channel_bridge.channel_factory.create_channel_instance",
            factory.create_channel_instance,
        ),
    ):
        await save_channel_credentials(channel_name, {"appSecret": "rotated"})

    gateway.remove_channel.assert_awaited_once_with(channel_name)
    factory.create_channel_instance.assert_awaited_once()
    create_kwargs = factory.create_channel_instance.await_args.kwargs
    assert create_kwargs["channel_type"] == "feishu"
    assert create_kwargs["instance_id"] == instance_id
    assert new_channel.display_name == "客服机器人"
    gateway.add_channel.assert_awaited_once_with(new_channel)

    config_key = channel_credentials_key(channel_name)
    record = await ConfigService().get(config_key)
    assert record is not None
    assert record.value["appSecret"] == "rotated"


@pytest.mark.asyncio
async def test_save_channel_credentials_default_instance_hot_reloads() -> None:
    """A default (non-instance) channel reloads via _try_hot_register_channel."""
    from app.api.channels.instances import save_channel_credentials
    from app.services.config.service import ConfigService

    await ConfigService().set(
        "feishuCredentials",
        {"appId": "cli_default", "appSecret": "old", "useLark": "false"},
        device_id="test",
    )

    try:
        gateway = MagicMock()
        gateway._resolve_channel_type = MagicMock(return_value="feishu")
        default_channel = MagicMock()
        default_channel.name = "feishu"
        default_channel.channel_type = "feishu"
        gateway.bus.get_channel = MagicMock(return_value=default_channel)

        with (
            patch("app.core.channel_bridge.channel_gateway", gateway),
            patch("app.api.config.router._try_hot_register_channel", new_callable=AsyncMock) as mock_hot,
        ):
            await save_channel_credentials("feishu", {"appSecret": "rotated_default"})

        mock_hot.assert_awaited_once_with("feishuCredentials")
        gateway.remove_channel.assert_not_called()

        record = await ConfigService().get("feishuCredentials")
        assert record is not None
        assert record.value["appSecret"] == "rotated_default"
    finally:
        await ConfigService().delete("feishuCredentials")


@pytest.mark.asyncio
async def test_get_channel_credentials_redacts_secret_fields() -> None:
    """Reading credentials returns decrypted values with secret fields redacted."""
    from app.api.channels.instances import get_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    channel_name = f"feishu_{uuid.uuid4().hex[:8]}"
    config_key = channel_credentials_key(channel_name)
    await ConfigService().set(
        config_key,
        {"appId": "cli_redact", "appSecret": "long_secret_value", "botOpenId": "ou_123"},
        device_id="test",
    )

    try:
        result = await get_channel_credentials(channel_name)
        assert result["appId"] == "cli_redact"
        assert result["appSecret"] == "•" * (len("long_secret_value") - 4) + "long_secret_value"[-4:]
        assert result["botOpenId"] == "ou_123"
    finally:
        await ConfigService().delete(config_key)
