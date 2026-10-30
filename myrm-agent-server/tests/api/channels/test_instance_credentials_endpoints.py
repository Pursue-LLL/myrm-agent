"""Instance creation persists its credentials, hot registration keeps the display name, the credentials read endpoint
redacts and normalizes, and the per-type instance limit is reported.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete

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
        await session.execute(delete(UserConfig))
        await session.commit()


@pytest.mark.asyncio
async def test_hot_register_preserves_display_name() -> None:
    """Hot-reloading a default channel must keep the user-set display name."""
    from app.services.channels.credential_reload import reload_channel_credentials
    from app.services.config.service import ConfigService

    await ConfigService().set(
        "feishuCredentials",
        {"appId": "cli_hot", "appSecret": "sec_hot", "useLark": "false"},
        device_id="test",
    )

    try:
        existing = MagicMock()
        existing.display_name = "我的飞书"

        replacement = MagicMock()

        gateway = MagicMock()
        gateway.bus.get_channel = MagicMock(return_value=existing)
        gateway.swap_channel = AsyncMock()

        cls = MagicMock()
        cls.credential_spec = MagicMock()
        cls.from_credentials = MagicMock(return_value=replacement)

        with (
            patch("app.core.channel_bridge.channel_gateway", gateway),
            patch("app.channels.providers.registry.get_channel_class_safe", return_value=cls),
            patch("app.channels.core.credentials.resolve_credentials", new=AsyncMock(return_value={"app_id": "cli_hot"})),
            patch("app.core.channel_bridge.credential_spec.is_channel_enabled", new=AsyncMock(return_value=True)),
        ):
            await reload_channel_credentials("feishuCredentials")

        assert replacement.display_name == "我的飞书"
        gateway.swap_channel.assert_awaited_once_with(replacement, existing)
    finally:
        await ConfigService().delete("feishuCredentials")


@pytest.mark.asyncio
async def test_hot_register_empty_credentials_keeps_channel() -> None:
    """When no credentials resolve, the registered channel must stay as-is
    instead of being removed and never re-added."""
    from app.services.channels.credential_reload import reload_channel_credentials

    gateway = MagicMock()
    existing = MagicMock()
    gateway.bus.get_channel = MagicMock(return_value=existing)

    with (
        patch("app.core.channel_bridge.channel_gateway", gateway),
        patch(
            "app.channels.providers.registry.get_channel_class_safe",
            return_value=MagicMock(credential_spec=MagicMock()),
        ),
        patch("app.channels.core.credentials.resolve_credentials", new=AsyncMock(return_value={"app_id": ""})),
    ):
        await reload_channel_credentials("feishuCredentials")

    gateway.remove_channel.assert_not_called()
    gateway.add_channel.assert_not_called()
    gateway.swap_channel.assert_not_called()


# ── get_channel_credentials ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_channel_credentials_redacts_secret_fields() -> None:
    """Reading credentials returns decrypted values with secret fields redacted."""
    from app.api.channels.instances_credentials import get_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    channel_name = f"feishu_{uuid.uuid4().hex[:8]}"
    config_key = channel_credentials_key(channel_name)
    await ConfigService().set(
        config_key,
        {"appId": "cli_redact", "appSecret": "long_secret_value"},
        device_id="test",
    )

    try:
        result = await get_channel_credentials(channel_name)
        assert result["appId"] == "cli_redact"
        assert result["appSecret"] == "•" * (len("long_secret_value") - 4) + "long_secret_value"[-4:]
    finally:
        await ConfigService().delete(config_key)


@pytest.mark.asyncio
async def test_get_channel_credentials_normalizes_boolean_use_lark() -> None:
    """Boolean credentials stored by the QR flow must be returned as lowercase
    strings so the frontend ``useLark === 'true'`` comparison is stable."""
    from app.api.channels.instances_credentials import get_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    channel_name = f"feishu_{uuid.uuid4().hex[:8]}"
    config_key = channel_credentials_key(channel_name)
    await ConfigService().set(
        config_key,
        {"appId": "cli_bool", "appSecret": "sec_bool", "useLark": True},
        device_id="test",
    )

    try:
        result = await get_channel_credentials(channel_name)
        assert result["useLark"] == "true"
        assert isinstance(result["useLark"], str)
    finally:
        await ConfigService().delete(config_key)


@pytest.mark.asyncio
async def test_hot_register_swap_failure_propagates_exception() -> None:
    """A failed swap must surface as an exception so the caller can log it
    instead of silently leaving the channel in a half-removed state. The
    atomic restore (old instance back online) is owned by the gateway's
    ``swap_channel``."""
    from app.services.channels.credential_reload import reload_channel_credentials
    from app.services.config.service import ConfigService

    await ConfigService().set(
        "feishuCredentials",
        {"appId": "cli_atomic", "appSecret": "sec_atomic", "useLark": "false"},
        device_id="test",
    )

    try:
        existing = MagicMock()
        existing.display_name = "我的飞书"

        replacement = MagicMock()

        gateway = MagicMock()
        gateway.bus.get_channel = MagicMock(return_value=existing)
        gateway.swap_channel = AsyncMock(side_effect=ValueError("add failed"))

        cls = MagicMock()
        cls.credential_spec = MagicMock()
        cls.from_credentials = MagicMock(return_value=replacement)

        with (
            patch("app.core.channel_bridge.channel_gateway", gateway),
            patch("app.channels.providers.registry.get_channel_class_safe", return_value=cls),
            patch("app.channels.core.credentials.resolve_credentials", new=AsyncMock(return_value={"app_id": "cli_atomic"})),
            patch("app.core.channel_bridge.credential_spec.is_channel_enabled", new=AsyncMock(return_value=True)),
        ):
            with pytest.raises(ValueError, match="add failed"):
                await reload_channel_credentials("feishuCredentials")

        gateway.swap_channel.assert_awaited_once_with(replacement, existing)
    finally:
        await ConfigService().delete("feishuCredentials")


@pytest.mark.asyncio
async def test_get_channel_instances_meta_returns_max_per_type() -> None:
    """The capacity endpoint must expose the backend per-type limit."""
    from app.api.channels.instances import get_channel_instances_meta

    gateway = MagicMock()
    gateway.max_instances_per_type = 5

    with patch("app.core.channel_bridge.channel_gateway", gateway):
        result = await get_channel_instances_meta()

    assert result == {"maxInstancesPerType": 5}
    assert gateway.max_instances_per_type == 5
