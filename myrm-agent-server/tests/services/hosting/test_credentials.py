"""Tests for hosting target credential helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hosting.credentials import (
    VERCEL_CREDENTIALS_KEY,
    decrypt_credentials,
    get_platform_vercel_token,
    has_any_hosting_credentials,
    load_legacy_vercel_token,
    load_target_credentials,
    resolve_target_credentials,
    save_target_credentials,
    token_from_credentials,
)


def test_token_from_credentials_returns_stripped_token() -> None:
    assert token_from_credentials({"token": "  abc  "}) == "abc"


def test_token_from_credentials_empty_when_missing() -> None:
    assert token_from_credentials({}) is None
    assert token_from_credentials({"token": "  "}) is None


def test_decrypt_credentials_plain_dict() -> None:
    result = decrypt_credentials({"token": "x"}, is_encrypted=False)
    assert result == {"token": "x"}


def test_decrypt_credentials_encrypted_string() -> None:
    mock_service = MagicMock()
    mock_service.decrypt.return_value = '{"token": "enc-tok"}'
    with patch("app.services.hosting.credentials.get_encryption_service", return_value=mock_service):
        result = decrypt_credentials("cipher-text", is_encrypted=True)
    assert result == {"token": "enc-tok"}


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
async def test_save_target_credentials_inserts_new_row() -> None:
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    with patch("app.services.hosting.credentials.get_encryption_service") as mock_service_factory:
        mock_service = mock_service_factory.return_value
        mock_service.encrypt_if_needed.return_value = ({"token": "saved-token"}, False)

        result = await save_target_credentials(mock_db, "target-abc", {"token": "saved-token"})

    assert result["status"] == "success"
    mock_db.add.assert_called_once()
    added = mock_db.add.call_args.args[0]
    assert added.config_key == "hostingTargetCredentials:target-abc"
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_target_credentials_empty_when_missing() -> None:
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    assert await load_target_credentials(mock_db, "target-x") == {}


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
