"""Tests for Feishu credential persistence and instance provisioning internals."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.api.channels.feishu_register import (
    _SESSION_TTL_S,
    _active_sessions,
    _cleanup_expired_sessions,
    _RegistrationSession,
)


@pytest.fixture(autouse=True)
def _clear_sessions() -> None:
    """Ensure session store is empty before each test."""
    _active_sessions.clear()


class TestSaveCredentialsToDb:
    @pytest.mark.asyncio
    async def test_save_uses_config_service(self) -> None:
        from app.api.channels.feishu_register import _save_credentials_to_db

        mock_set = AsyncMock()
        with patch("app.services.config.service.ConfigService") as mock_cls:
            mock_cls.return_value.set = mock_set
            with patch("app.api.config.router._try_hot_register_channel", new_callable=AsyncMock) as mock_hot:
                await _save_credentials_to_db(
                    {
                        "app_id": "cli_test",
                        "app_secret": "sec_test",
                        "domain": "feishu",
                        "bot_open_id": "ou_bot",
                    }
                )
        mock_set.assert_awaited_once()
        call_args = mock_set.await_args
        assert call_args is not None
        assert call_args.args[0] == "feishuCredentials"
        assert call_args.args[1]["appId"] == "cli_test"
        assert call_args.args[1]["transport"] == "websocket"
        mock_hot.assert_awaited_once_with("feishuCredentials")


class TestSessionCleanup:
    def test_cleanup_expired_sessions(self) -> None:
        import time

        mock_reg = AsyncMock()

        session = _RegistrationSession(registration=mock_reg, device_code="dc_old")
        session.created_at = time.monotonic() - _SESSION_TTL_S - 10

        _active_sessions["old_session"] = session
        _active_sessions["new_session"] = _RegistrationSession(registration=mock_reg, device_code="dc_new")

        _cleanup_expired_sessions()

        assert "old_session" not in _active_sessions
        assert "new_session" in _active_sessions

    def test_cleanup_empty_sessions(self) -> None:
        _cleanup_expired_sessions()
        assert len(_active_sessions) == 0


class TestProvisionRollback:
    @pytest.mark.asyncio
    async def test_provision_rolls_back_credentials_on_add_channel_failure(self) -> None:
        """A failed provisioning must delete the persisted credentials key."""
        from app.api.channels.feishu_register import _provision_feishu_instance

        value = {"appId": "cli_rollback", "appSecret": "sec_rollback", "useLark": False}

        with (
            patch("app.services.config.service.ConfigService") as mock_config_cls,
            patch("app.core.channel_bridge.channel_gateway") as mock_gateway,
        ):
            mock_config_cls.return_value.set = AsyncMock()
            mock_config_cls.return_value.delete = AsyncMock()

            mock_channel = AsyncMock()
            mock_gateway.add_channel = AsyncMock(side_effect=ValueError("Instance limit reached"))

            with patch(
                "app.core.channel_bridge.channel_factory.create_channel_instance",
                new_callable=AsyncMock,
                return_value=mock_channel,
            ):
                with pytest.raises(ValueError, match="Instance limit reached"):
                    await _provision_feishu_instance(value, "Rollback App")

        # Credentials must have been rolled back, and only after set() was called.
        mock_config_cls.return_value.delete.assert_awaited_once()
        set_call = mock_config_cls.return_value.set.await_args
        assert set_call is not None
        assert mock_config_cls.return_value.delete.await_args.args[0] == set_call.args[0]
        # add_channel failed before registration, so no remove_channel should be attempted.
        mock_gateway.remove_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_rolls_back_channel_when_persistence_fails(self) -> None:
        """A failure after hot-registration must also remove the channel from the gateway."""
        from app.api.channels.feishu_register import _provision_feishu_instance

        value = {"appId": "cli_persist", "appSecret": "sec_persist", "useLark": False}

        with (
            patch("app.services.config.service.ConfigService") as mock_config_cls,
            patch("app.core.channel_bridge.channel_gateway") as mock_gateway,
        ):
            mock_config_cls.return_value.set = AsyncMock()
            mock_config_cls.return_value.delete = AsyncMock()

            mock_channel = AsyncMock()
            mock_channel.name = "feishu_persist"
            mock_channel.instance_id = "inst_persist"
            mock_gateway.add_channel = AsyncMock(return_value="feishu_persist")
            mock_gateway.remove_channel = AsyncMock(return_value=True)

            with (
                patch(
                    "app.core.channel_bridge.channel_factory.create_channel_instance",
                    new_callable=AsyncMock,
                    return_value=mock_channel,
                ),
                patch(
                    "app.core.channel_bridge.channel_factory.load_persisted_instances",
                    new_callable=AsyncMock,
                    side_effect=RuntimeError("db unavailable"),
                ),
                patch(
                    "app.core.channel_bridge.channel_factory.save_persisted_instances",
                    new_callable=AsyncMock,
                ),
            ):
                with pytest.raises(RuntimeError, match="db unavailable"):
                    await _provision_feishu_instance(value, "Persist App")

        # Credentials deleted AND the already-registered channel removed.
        mock_config_cls.return_value.delete.assert_awaited_once()
        mock_gateway.remove_channel.assert_awaited_once_with("feishu_persist")

    @pytest.mark.asyncio
    async def test_provision_flattens_bool_credentials_to_lowercase(self) -> None:
        """Boolean credentials must be rendered as lowercase strings (useLark=false)."""
        from app.api.channels.feishu_register import _provision_feishu_instance

        value = {"appId": "cli_bool", "appSecret": "sec_bool", "useLark": False}

        with (
            patch("app.services.config.service.ConfigService") as mock_config_cls,
            patch("app.core.channel_bridge.channel_gateway") as mock_gateway,
        ):
            mock_config_cls.return_value.set = AsyncMock()

            mock_channel = AsyncMock()
            mock_channel.name = "feishu_booltest"
            mock_channel.instance_id = "inst_bool_1"
            mock_gateway.add_channel = AsyncMock(return_value="feishu_booltest")

            with (
                patch(
                    "app.core.channel_bridge.channel_factory.create_channel_instance",
                    new_callable=AsyncMock,
                    return_value=mock_channel,
                ) as mock_factory,
                patch(
                    "app.core.channel_bridge.channel_factory.load_persisted_instances",
                    new_callable=AsyncMock,
                    return_value=[],
                ),
                patch(
                    "app.core.channel_bridge.channel_factory.save_persisted_instances",
                    new_callable=AsyncMock,
                ),
                patch(
                    "app.core.channel_bridge.channel_factory.generate_instance_id",
                    return_value="inst_bool_1",
                ),
            ):
                result = await _provision_feishu_instance(value, "Bool App")

        assert result == {"instanceId": "inst_bool_1", "channelName": "feishu_booltest"}
        _, factory_kwargs = mock_factory.call_args
        assert factory_kwargs["credentials"]["useLark"] == "false"
        assert factory_kwargs["credentials"]["appId"] == "cli_bool"
