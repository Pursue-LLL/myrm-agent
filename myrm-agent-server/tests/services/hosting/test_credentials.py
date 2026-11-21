"""Tests for hosting target credential helpers, under the real sealing policy."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.config import UserConfig
from app.services.config.encryption import ConfigEncryptionService
from app.services.config.migration import migrate_configs_to_encrypted
from app.services.hosting.credentials import (
    VERCEL_CREDENTIALS_KEY,
    decrypt_credentials,
    get_platform_vercel_token,
    get_target_credential_status,
    has_any_hosting_credentials,
    load_credentials_row,
    load_legacy_vercel_token,
    load_target_credentials,
    migrate_legacy_vercel_credentials,
    resolve_target_credentials,
    save_target_credentials,
    token_from_credentials,
)
from app.services.hosting.targets import (
    credential_config_key,
    save_hosting_targets,
)
from app.services.hosting.types import HostingTarget


def _vercel(target_id: str, *, is_default: bool = False) -> HostingTarget:
    return HostingTarget(id=target_id, name=target_id, provider_type="vercel", config={}, is_default=is_default)


def _plain_row(row_id: str, key: str, value: dict[str, object]) -> UserConfig:
    return UserConfig(id=row_id, config_key=key, config_value=value, version="1.0.0", last_device_id="webui", is_encrypted=False)


def test_token_from_credentials_returns_stripped_token() -> None:
    assert token_from_credentials({"token": "  abc  "}) == "abc"


def test_token_from_credentials_empty_when_missing() -> None:
    assert token_from_credentials({}) is None
    assert token_from_credentials({"token": "  "}) is None


def test_decrypt_credentials_plain_dict() -> None:
    result = decrypt_credentials({"token": "x"}, is_encrypted=False)
    assert result == {"token": "x"}


def test_decrypt_credentials_opens_a_sealed_value_and_its_envelope(real_encryption: ConfigEncryptionService) -> None:
    sealed, is_encrypted = real_encryption.encrypt_if_needed(credential_config_key("t"), {"token": "enc-tok"})
    assert is_encrypted

    assert decrypt_credentials(sealed, is_encrypted=True) == {"token": "enc-tok"}
    assert decrypt_credentials({"_cipher": sealed}, is_encrypted=True) == {"token": "enc-tok"}


def test_get_platform_vercel_token_non_sandbox() -> None:
    with patch("app.services.hosting.credentials.is_sandbox", return_value=False):
        assert get_platform_vercel_token() is None


def test_get_platform_vercel_token_sandbox_with_env() -> None:
    with (
        patch("app.services.hosting.credentials.is_sandbox", return_value=True),
        patch.dict("os.environ", {"VERCEL_PLATFORM_TOKEN": "  plat-tok  "}, clear=False),
    ):
        assert get_platform_vercel_token() == "plat-tok"


@pytest.mark.asyncio
async def test_load_legacy_vercel_token_returns_none_when_missing() -> None:
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    assert await load_legacy_vercel_token(mock_db) is None


@pytest.mark.asyncio
async def test_resolve_target_credentials_prefers_request_token() -> None:
    mock_db = AsyncMock()
    creds = await resolve_target_credentials(mock_db, "target-1", request_token="  body-tok  ")
    assert creds == {"token": "body-tok"}


@pytest.mark.asyncio
async def test_resolve_target_credentials_raises_when_missing() -> None:
    mock_db = AsyncMock()
    with (
        patch("app.services.hosting.credentials.load_target_credentials", AsyncMock(return_value={})),
        patch("app.services.hosting.credentials.get_hosting_target", AsyncMock(return_value=None)),
    ):
        with pytest.raises(RuntimeError, match="Hosting credentials not configured"):
            await resolve_target_credentials(mock_db, "missing-target", request_token="")


@pytest.mark.asyncio
async def test_has_any_hosting_credentials_platform_token() -> None:
    with patch("app.services.hosting.credentials.get_platform_vercel_token", return_value="plat"):
        assert await has_any_hosting_credentials() is True


@pytest.mark.asyncio
async def test_saved_credentials_are_sealed_at_rest(db_session: AsyncSession) -> None:
    await save_target_credentials(db_session, "t1", {"token": "saved-token"})

    row = await load_credentials_row(db_session, "t1")
    assert row is not None
    assert row.config_key == "hostingTargetCredentials:t1"
    assert row.is_encrypted is True
    assert "saved-token" not in json.dumps(row.config_value)
    assert await load_target_credentials(db_session, "t1") == {"token": "saved-token"}


@pytest.mark.asyncio
async def test_saving_again_replaces_the_row_instead_of_adding_one(db_session: AsyncSession) -> None:
    await save_target_credentials(db_session, "t1", {"token": "first"})
    await save_target_credentials(db_session, "t1", {"token": "second"})

    count = await db_session.scalar(
        select(func.count()).select_from(UserConfig).where(UserConfig.config_key == credential_config_key("t1"))
    )
    assert count == 1
    assert await load_target_credentials(db_session, "t1") == {"token": "second"}


@pytest.mark.asyncio
async def test_startup_sweep_seals_credentials_rows_saved_in_plaintext(db_session: AsyncSession) -> None:
    db_session.add(_plain_row("saved-before-sealing", credential_config_key("t1"), {"token": "plain-token"}))
    await db_session.commit()

    stats = await migrate_configs_to_encrypted(db_session)

    row = await load_credentials_row(db_session, "t1")
    assert stats["migrated"] == 1
    assert row is not None
    assert row.is_encrypted is True
    assert "plain-token" not in json.dumps(row.config_value)
    assert await load_target_credentials(db_session, "t1") == {"token": "plain-token"}


@pytest.mark.asyncio
async def test_load_target_credentials_empty_when_missing(db_session: AsyncSession) -> None:
    assert await load_target_credentials(db_session, "target-x") == {}


@pytest.mark.asyncio
async def test_migrate_legacy_uses_vercel_key() -> None:
    from app.services.hosting.credentials import migrate_legacy_vercel_credentials

    mock_row = MagicMock()
    mock_row.config_value = {"token": "legacy"}
    mock_row.is_encrypted = False
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_row
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with (
        patch("app.services.hosting.credentials.list_hosting_targets", AsyncMock(return_value=[])),
        patch("app.services.hosting.credentials.save_hosting_targets", AsyncMock()),
        patch("app.services.hosting.credentials.save_target_credentials", AsyncMock()) as mock_save,
    ):
        await migrate_legacy_vercel_credentials(mock_db)
    mock_save.assert_awaited_once()
    assert mock_save.call_args.args[2] == {"token": "legacy"}


def test_vercel_legacy_key_constant() -> None:
    assert VERCEL_CREDENTIALS_KEY == "vercelDeployCredentials"


@pytest.mark.asyncio
async def test_get_target_credential_status_configured(db_session: AsyncSession) -> None:
    await save_hosting_targets(db_session, [_vercel("t1", is_default=True)])
    await save_target_credentials(db_session, "t1", {"token": "saved"})
    status = await get_target_credential_status(db_session, "t1")
    assert status.configured is True


@pytest.mark.asyncio
async def test_resolve_target_credentials_webhook_empty_ok() -> None:
    mock_db = AsyncMock()
    webhook_target = HostingTarget(
        id="wh-1",
        name="Hook",
        provider_type="http_webhook",
        config={"webhook_url": "https://example.com/hook"},
        is_default=True,
    )
    with (
        patch("app.services.hosting.credentials.load_target_credentials", AsyncMock(return_value={})),
        patch("app.services.hosting.credentials.get_hosting_target", AsyncMock(return_value=webhook_target)),
    ):
        creds = await resolve_target_credentials(mock_db, "wh-1", request_token="")
    assert creds == {}


@pytest.mark.asyncio
async def test_migrate_legacy_skips_when_targets_exist() -> None:
    mock_db = AsyncMock()
    with (
        patch("app.services.hosting.credentials.load_legacy_vercel_token", AsyncMock(return_value="legacy")),
        patch("app.services.hosting.credentials.list_hosting_targets", AsyncMock(return_value=[object()])),
        patch("app.services.hosting.credentials.save_hosting_targets", AsyncMock()) as mock_save,
    ):
        await migrate_legacy_vercel_credentials(mock_db)
    mock_save.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_target_credentials_legacy_vercel() -> None:
    mock_db = AsyncMock()
    legacy_target = HostingTarget(id="legacy", name="V", provider_type="vercel", config={}, is_default=True)
    with (
        patch("app.services.hosting.credentials.load_target_credentials", AsyncMock(return_value={})),
        patch("app.services.hosting.credentials.get_hosting_target", AsyncMock(return_value=legacy_target)),
        patch("app.services.hosting.credentials.load_legacy_vercel_token", AsyncMock(return_value="legacy-tok")),
    ):
        creds = await resolve_target_credentials(mock_db, "legacy", request_token="")
    assert creds == {"token": "legacy-tok"}
