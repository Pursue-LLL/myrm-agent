"""Tests for idempotent config sync when content matches despite version mismatch."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.config.service import VersionConflictError, _config_values_equal, config_service


def _mock_session_factory(existing: MagicMock | None) -> MagicMock:
    session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = existing
    session.execute = AsyncMock(return_value=execute_result)

    session_factory = MagicMock()
    session_factory.return_value.__aenter__ = AsyncMock(return_value=session)
    session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return session_factory


class TestConfigValuesEqual:
    def test_equal_dicts_different_key_order(self) -> None:
        assert _config_values_equal({"a": 1, "b": 2}, {"b": 2, "a": 1}) is True

    def test_not_equal(self) -> None:
        assert _config_values_equal({"a": 1}, {"a": 2}) is False


@pytest.mark.asyncio
async def test_set_accepts_idempotent_sync_on_version_mismatch() -> None:
    existing = MagicMock()
    existing.version = "2000_1"
    existing.config_value = {"enabled": True}
    existing.is_encrypted = False
    existing.config_key = "personalSettings"

    session_factory = _mock_session_factory(existing)
    built_record = MagicMock(version="2000_1")

    with (
        patch("app.services.config.service.get_session_factory", return_value=session_factory),
        patch("app.services.config.service._encrypt_if_sensitive", return_value=({"enabled": True}, False)),
        patch("app.services.config.service._decrypt_if_needed", return_value={"enabled": True}),
        patch("app.services.config.service._build_config_record", return_value=built_record) as mock_build,
    ):
        result = await config_service.set(
            config_key="personalSettings",
            value={"enabled": True},
            device_id="device-b",
            expected_version="1000_0",
        )

        assert result is built_record
        mock_build.assert_called_once_with(existing, {"enabled": True})


@pytest.mark.asyncio
async def test_set_raises_on_version_mismatch_and_content_diff() -> None:
    existing = MagicMock()
    existing.version = "2000_1"
    existing.config_value = {"enabled": True}
    existing.is_encrypted = False

    session_factory = _mock_session_factory(existing)

    with (
        patch("app.services.config.service.get_session_factory", return_value=session_factory),
        patch("app.services.config.service._encrypt_if_sensitive", return_value=({"enabled": False}, False)),
        patch("app.services.config.service._decrypt_if_needed", return_value={"enabled": True}),
    ):
        with pytest.raises(VersionConflictError):
            await config_service.set(
                config_key="personalSettings",
                value={"enabled": False},
                device_id="device-b",
                expected_version="1000_0",
            )
