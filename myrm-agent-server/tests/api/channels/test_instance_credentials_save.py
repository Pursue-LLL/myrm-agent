"""``save_channel_credentials``: instance keys are stored encrypted, a save merges into what is stored, and the
running channel is rebuilt, reloaded or registered so the new credentials take effect.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete

# ── save_channel_credentials ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_channel_credentials_encrypts_instance_key() -> None:
    """The credentials endpoint must store instance keys encrypted at rest."""
    from sqlalchemy import select

    from app.api.channels.instances_credentials import save_channel_credentials
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
        row = (await session.execute(select(UserConfig).where(UserConfig.config_key == config_key))).scalar_one_or_none()
    assert row is not None
    assert row.is_encrypted is True
    assert "_cipher" in row.config_value

    async with get_session() as session:
        await session.execute(delete(UserConfig))
        await session.commit()


@pytest.mark.asyncio
async def test_save_channel_credentials_merge_preserves_omitted_fields() -> None:
    """Only submitted fields are overwritten; omitted keys survive the update."""
    from app.api.channels.instances_credentials import save_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    channel_name = f"feishu_{uuid.uuid4().hex[:8]}"
    config_key = channel_credentials_key(channel_name)
    await ConfigService().set(
        config_key,
        {"appId": "cli_keep", "appSecret": "old_secret", "verificationToken": "vt_keep", "useLark": "false"},
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
        assert record.value["verificationToken"] == "vt_keep"
        assert record.value["useLark"] == "false"
    finally:
        await ConfigService().delete(config_key)


@pytest.mark.asyncio
async def test_save_channel_credentials_rebuilds_multi_instance() -> None:
    """A registered multi-app instance must be recreated from merged credentials
    with the same instance id (so the channel name and agent bindings survive)."""
    from app.api.channels.instances_credentials import save_channel_credentials
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
    gateway.swap_channel = AsyncMock()

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

    factory.create_channel_instance.assert_awaited_once()
    create_kwargs = factory.create_channel_instance.await_args.kwargs
    assert create_kwargs["channel_type"] == "feishu"
    assert create_kwargs["instance_id"] == instance_id
    assert new_channel.display_name == "客服机器人"
    # The swap is delegated to the gateway's atomic swap_channel so the old
    # instance is restored if the replacement fails to register.
    gateway.swap_channel.assert_awaited_once_with(new_channel, old_channel)

    config_key = channel_credentials_key(channel_name)
    record = await ConfigService().get(config_key)
    assert record is not None
    assert record.value["appSecret"] == "rotated"


@pytest.mark.asyncio
async def test_save_channel_credentials_rebuild_passes_string_credentials() -> None:
    """Credentials stored as booleans (QR flow) reach the channel factory as
    lowercase strings, the same shape the other provisioning paths use."""
    from app.api.channels.instances_credentials import save_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    instance_id = uuid.uuid4().hex[:8]
    channel_name = f"feishu_{instance_id}"
    config_key = channel_credentials_key(channel_name)
    await ConfigService().set(
        config_key,
        {"appId": "cli_flat", "appSecret": "old", "useLark": True},
        device_id="test",
    )

    old_channel = MagicMock()
    old_channel.instance_id = instance_id
    old_channel.display_name = "flat"

    gateway = MagicMock()
    gateway._resolve_channel_type = MagicMock(return_value="feishu")
    gateway.bus.get_channel = MagicMock(return_value=old_channel)
    gateway.swap_channel = AsyncMock()

    create = AsyncMock(return_value=MagicMock())

    try:
        with (
            patch("app.core.channel_bridge.channel_gateway", gateway),
            patch("app.core.channel_bridge.channel_factory.create_channel_instance", create),
        ):
            await save_channel_credentials(channel_name, {"appSecret": "rotated"})
    finally:
        await ConfigService().delete(config_key)

    assert create.await_args is not None
    assert create.await_args.kwargs["credentials"] == {
        "appId": "cli_flat",
        "appSecret": "rotated",
        "useLark": "true",
    }


@pytest.mark.asyncio
async def test_save_channel_credentials_default_instance_hot_reloads() -> None:
    """A default (non-instance) channel reloads via reload_channel_credentials."""
    from app.api.channels.instances_credentials import save_channel_credentials
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
            patch("app.services.channels.credential_reload.reload_channel_credentials", new_callable=AsyncMock) as mock_hot,
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
async def test_save_channel_credentials_unregistered_channel_hot_registers() -> None:
    """An unregistered channel must still trigger a hot-register attempt so the
    update takes effect without a restart (e.g. first-time provisioning)."""
    from app.api.channels.instances_credentials import save_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    channel_name = "feishu"
    config_key = channel_credentials_key(channel_name)
    assert config_key == "feishuCredentials"
    await ConfigService().set(
        config_key,
        {"appId": "cli_first", "appSecret": "sec_first", "useLark": "false"},
        device_id="test",
    )

    try:
        gateway = MagicMock()
        gateway.bus.get_channel = MagicMock(return_value=None)

        with (
            patch("app.core.channel_bridge.channel_gateway", gateway),
            patch("app.services.channels.credential_reload.reload_channel_credentials", new_callable=AsyncMock) as mock_hot,
        ):
            result = await save_channel_credentials(channel_name, {"appSecret": "rotated_first"})

        assert result["status"] == "saved"
        mock_hot.assert_awaited_once_with("feishuCredentials")

        record = await ConfigService().get(config_key)
        assert record is not None
        assert record.value["appSecret"] == "rotated_first"
    finally:
        await ConfigService().delete(config_key)


@pytest.mark.asyncio
async def test_save_channel_credentials_rebuild_failure_preserves_old_channel() -> None:
    """A construction failure must NOT remove the running channel: the rebuild
    happens before remove_channel, so a bad credential payload leaves the
    existing instance untouched instead of orphaning it."""
    from app.api.channels.instances_credentials import save_channel_credentials
    from app.api.channels.router import channel_credentials_key
    from app.services.config.service import ConfigService

    instance_id = uuid.uuid4().hex[:8]
    channel_name = f"feishu_{instance_id}"

    old_channel = MagicMock()
    old_channel.name = channel_name
    old_channel.channel_type = "feishu"
    old_channel.instance_id = instance_id
    old_channel.display_name = "客服机器人"

    gateway = MagicMock()
    gateway._resolve_channel_type = MagicMock(return_value="feishu")
    gateway.bus.get_channel = MagicMock(return_value=old_channel)

    factory = MagicMock()
    factory.create_channel_instance = AsyncMock(side_effect=ValueError("app_id cannot be empty"))

    with (
        patch("app.core.channel_bridge.channel_gateway", gateway),
        patch(
            "app.core.channel_bridge.channel_factory.create_channel_instance",
            factory.create_channel_instance,
        ),
    ):
        result = await save_channel_credentials(channel_name, {"appSecret": "rotated"})

    assert result["status"] == "saved"
    gateway.remove_channel.assert_not_called()
    gateway.add_channel.assert_not_called()
    gateway.swap_channel.assert_not_called()

    config_key = channel_credentials_key(channel_name)
    record = await ConfigService().get(config_key)
    assert record is not None
    assert record.value["appSecret"] == "rotated"


@pytest.mark.asyncio
async def test_save_channel_credentials_rebuild_swap_failure_keeps_credentials() -> None:
    """A failed atomic swap must not surface to the client: the merged
    credentials are already persisted and take effect on the next startup,
    while the atomic restore (old instance back online) is owned by the
    gateway's ``swap_channel``."""
    from app.api.channels.instances_credentials import save_channel_credentials
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
    gateway.swap_channel = AsyncMock(side_effect=ValueError("add failed"))

    factory = MagicMock()
    factory.create_channel_instance = AsyncMock(return_value=new_channel)

    with (
        patch("app.core.channel_bridge.channel_gateway", gateway),
        patch(
            "app.core.channel_bridge.channel_factory.create_channel_instance",
            factory.create_channel_instance,
        ),
    ):
        result = await save_channel_credentials(channel_name, {"appSecret": "rotated"})

    # The failure is logged (not surfaced to the client) since the merged
    # credentials were already persisted for the next startup.
    assert result["status"] == "saved"
    gateway.swap_channel.assert_awaited_once_with(new_channel, old_channel)

    config_key = channel_credentials_key(channel_name)
    record = await ConfigService().get(config_key)
    assert record is not None
    assert record.value["appSecret"] == "rotated"
