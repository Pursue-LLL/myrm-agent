"""Tests for oauth_store integration helpers."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge import config_cache
from app.database.models import UserConfig
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import (
    CONFIG_KEY,
    is_oauth_issuer_connected,
    persist_credentials_locked,
)


@pytest.mark.asyncio
async def test_is_oauth_issuer_connected_false_when_no_row() -> None:
    db = AsyncMock()
    with patch(
        "app.services.integrations.oauth_store.load_oauth_credentials_row",
        AsyncMock(return_value=None),
    ):
        assert await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER) is False


@pytest.mark.asyncio
async def test_is_oauth_issuer_connected_false_when_no_token() -> None:
    db = AsyncMock()
    row = MagicMock()
    row.config_value = {GOOGLE_WORKSPACE_ISSUER: {"refresh_token": "x"}}
    row.is_encrypted = False
    with patch(
        "app.services.integrations.oauth_store.load_oauth_credentials_row",
        AsyncMock(return_value=row),
    ):
        assert await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER) is False


@pytest.mark.asyncio
async def test_is_oauth_issuer_connected_true_when_token_present() -> None:
    db = AsyncMock()
    row = MagicMock()
    row.config_value = {GOOGLE_WORKSPACE_ISSUER: {"token": "access-token"}}
    row.is_encrypted = False
    with patch(
        "app.services.integrations.oauth_store.load_oauth_credentials_row",
        AsyncMock(return_value=row),
    ):
        assert await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER) is True


class TestPersistInvalidatesLoadedConfigs:
    """oauthCredentials writes must not leave the 30 s loaded-config snapshot serving stale tokens."""

    @staticmethod
    def _db_and_service() -> tuple[AsyncMock, MagicMock]:
        db = AsyncMock()
        db.add = MagicMock()
        service = MagicMock()
        service.encrypt_if_needed.return_value = ({"xai": {"token": "t"}}, False)
        return db, service

    @pytest.mark.asyncio
    async def test_commit_is_followed_by_cache_invalidation(self) -> None:
        db, service = self._db_and_service()
        order: list[str] = []
        db.commit.side_effect = lambda: order.append("commit")

        with (
            patch("app.services.integrations.oauth_store.get_encryption_service", return_value=service),
            patch(
                "app.core.channel_bridge.config_cache.invalidate_user_configs_cache",
                side_effect=lambda: order.append("invalidate"),
            ),
        ):
            await persist_credentials_locked(db, None, {"xai": {"token": "t"}})

        assert order == ["commit", "invalidate"]

    @pytest.mark.asyncio
    async def test_real_snapshot_is_dropped(self) -> None:
        db, service = self._db_and_service()
        config_cache._config_cache["sandbox"] = (time.monotonic(), MagicMock())

        with patch("app.services.integrations.oauth_store.get_encryption_service", return_value=service):
            await persist_credentials_locked(db, None, {"xai": {"token": "t"}})

        assert "sandbox" not in config_cache._config_cache

    @pytest.mark.asyncio
    async def test_other_config_keys_do_not_invalidate(self) -> None:
        db, service = self._db_and_service()

        with (
            patch("app.services.integrations.oauth_store.get_encryption_service", return_value=service),
            patch("app.core.channel_bridge.config_cache.invalidate_user_configs_cache") as invalidate,
        ):
            await persist_credentials_locked(db, None, {"srv": {"token": "t"}}, config_key="mcpOAuthTokens")

        assert CONFIG_KEY != "mcpOAuthTokens"
        invalidate.assert_not_called()
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalidation_failure_does_not_mask_the_committed_write(self) -> None:
        db, service = self._db_and_service()

        with (
            patch("app.services.integrations.oauth_store.get_encryption_service", return_value=service),
            patch(
                "app.core.channel_bridge.config_cache.invalidate_user_configs_cache",
                side_effect=RuntimeError("cache backend down"),
            ),
        ):
            await persist_credentials_locked(db, None, {"xai": {"token": "t"}})

        db.commit.assert_awaited_once()


class TestPersistedValueShape:
    """Plain credentials are stored as-is; ciphertext is stored inside a ``_cipher`` envelope."""

    @staticmethod
    def _service(encrypted: tuple[dict[str, object] | str, bool]) -> MagicMock:
        service = MagicMock()
        service.encrypt_if_needed.return_value = encrypted
        return service

    @pytest.mark.asyncio
    async def test_ciphertext_is_wrapped_on_an_existing_row(self) -> None:
        row = UserConfig(
            id="row",
            config_key=CONFIG_KEY,
            config_value={},
            version="1.0.0",
            last_device_id="sandbox",
            is_encrypted=False,
        )

        with (
            patch(
                "app.services.integrations.oauth_store.get_encryption_service",
                return_value=self._service(("ciphertext", True)),
            ),
            patch("app.core.channel_bridge.config_cache.invalidate_user_configs_cache"),
        ):
            await persist_credentials_locked(AsyncMock(), row, {"xai": {"token": "t"}})

        assert row.config_value == {"_cipher": "ciphertext"}
        assert row.is_encrypted is True

    @pytest.mark.asyncio
    async def test_plain_credentials_are_stored_as_is_on_a_new_row(self) -> None:
        db = AsyncMock()
        db.add = MagicMock()
        credentials: dict[str, object] = {"srv": {"token": "t"}}

        with patch(
            "app.services.integrations.oauth_store.get_encryption_service",
            return_value=self._service((credentials, False)),
        ):
            await persist_credentials_locked(db, None, credentials, config_key="mcpOAuthTokens")

        created = db.add.call_args.args[0]
        assert created.config_value == credentials
        assert created.is_encrypted is False
