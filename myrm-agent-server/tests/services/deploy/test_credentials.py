"""Tests for Vercel deploy credential helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.deploy.credentials import (
    VERCEL_CREDENTIALS_KEY,
    decrypt_vercel_credentials,
    get_platform_vercel_token,
    has_deploy_credentials,
    load_stored_vercel_token,
    load_vercel_credentials_row,
    resolve_vercel_token,
    save_vercel_credentials,
    token_from_credentials_dict,
)


def test_token_from_credentials_dict_returns_stripped_token() -> None:
    assert token_from_credentials_dict({"token": "  abc  "}) == "abc"


def test_token_from_credentials_dict_empty_when_missing() -> None:
    assert token_from_credentials_dict({}) is None
    assert token_from_credentials_dict({"token": "  "}) is None


def test_decrypt_vercel_credentials_plain_dict() -> None:
    result = decrypt_vercel_credentials({"token": "x"}, is_encrypted=False)
    assert result == {"token": "x"}


def test_decrypt_vercel_credentials_encrypted_string() -> None:
    mock_service = MagicMock()
    mock_service.decrypt.return_value = '{"token": "enc-tok"}'
    with patch("app.services.deploy.credentials.get_encryption_service", return_value=mock_service):
        result = decrypt_vercel_credentials("cipher-text", is_encrypted=True)
    assert result == {"token": "enc-tok"}


def test_decrypt_vercel_credentials_encrypted_cipher_dict() -> None:
    mock_service = MagicMock()
    mock_service.decrypt.return_value = '{"token": "dict-tok"}'
    with patch("app.services.deploy.credentials.get_encryption_service", return_value=mock_service):
        result = decrypt_vercel_credentials({"_cipher": "payload"}, is_encrypted=True)
    assert result == {"token": "dict-tok"}


def test_decrypt_vercel_credentials_invalid_json_returns_empty() -> None:
    with patch("app.services.deploy.credentials.get_encryption_service"):
        result = decrypt_vercel_credentials("not-json", is_encrypted=False)
    assert result == {}


def test_decrypt_vercel_credentials_non_dict_returns_empty() -> None:
    result = decrypt_vercel_credentials(["not", "a", "dict"], is_encrypted=False)
    assert result == {}


def test_get_platform_vercel_token_non_sandbox() -> None:
    with patch("app.services.deploy.credentials.is_sandbox", return_value=False):
        assert get_platform_vercel_token() is None


def test_get_platform_vercel_token_sandbox_with_env() -> None:
    with (
        patch("app.services.deploy.credentials.is_sandbox", return_value=True),
        patch.dict("os.environ", {"VERCEL_PLATFORM_TOKEN": "  plat-tok  "}, clear=False),
    ):
        assert get_platform_vercel_token() == "plat-tok"


def test_get_platform_vercel_token_sandbox_empty_env() -> None:
    with (
        patch("app.services.deploy.credentials.is_sandbox", return_value=True),
        patch.dict("os.environ", {"VERCEL_PLATFORM_TOKEN": "   "}, clear=False),
    ):
        assert get_platform_vercel_token() is None


@pytest.mark.asyncio
async def test_load_vercel_credentials_row() -> None:
    mock_row = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_row
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    row = await load_vercel_credentials_row(mock_db)
    assert row is mock_row


@pytest.mark.asyncio
async def test_load_stored_vercel_token_returns_none_when_missing() -> None:
    mock_db = AsyncMock()
    with patch(
        "app.services.deploy.credentials.load_vercel_credentials_row",
        AsyncMock(return_value=None),
    ):
        assert await load_stored_vercel_token(mock_db) is None


@pytest.mark.asyncio
async def test_load_stored_vercel_token_returns_token() -> None:
    mock_row = MagicMock()
    mock_row.config_value = {"token": "stored"}
    mock_row.is_encrypted = False
    mock_db = AsyncMock()
    with patch(
        "app.services.deploy.credentials.load_vercel_credentials_row",
        AsyncMock(return_value=mock_row),
    ):
        assert await load_stored_vercel_token(mock_db) == "stored"


@pytest.mark.asyncio
async def test_resolve_vercel_token_prefers_request_body() -> None:
    mock_db = AsyncMock()
    token = await resolve_vercel_token(mock_db, "  body-tok  ")
    assert token == "body-tok"


@pytest.mark.asyncio
async def test_resolve_vercel_token_uses_stored() -> None:
    mock_db = AsyncMock()
    with patch(
        "app.services.deploy.credentials.load_stored_vercel_token",
        AsyncMock(return_value="stored-tok"),
    ):
        token = await resolve_vercel_token(mock_db, "")
    assert token == "stored-tok"


@pytest.mark.asyncio
async def test_resolve_vercel_token_uses_platform() -> None:
    mock_db = AsyncMock()
    with (
        patch("app.services.deploy.credentials.load_stored_vercel_token", AsyncMock(return_value=None)),
        patch("app.services.deploy.credentials.get_platform_vercel_token", return_value="plat-tok"),
    ):
        token = await resolve_vercel_token(mock_db, "")
    assert token == "plat-tok"


@pytest.mark.asyncio
async def test_resolve_vercel_token_raises_when_missing() -> None:
    mock_db = AsyncMock()
    with (
        patch("app.services.deploy.credentials.load_stored_vercel_token", AsyncMock(return_value=None)),
        patch("app.services.deploy.credentials.get_platform_vercel_token", return_value=None),
    ):
        with pytest.raises(RuntimeError, match="Vercel token not configured"):
            await resolve_vercel_token(mock_db, "")


@pytest.mark.asyncio
async def test_has_deploy_credentials_platform_token() -> None:
    with patch("app.services.deploy.credentials.get_platform_vercel_token", return_value="plat"):
        assert await has_deploy_credentials() is True


@pytest.mark.asyncio
async def test_has_deploy_credentials_stored_token() -> None:
    mock_db = MagicMock()
    with (
        patch("app.services.deploy.credentials.get_platform_vercel_token", return_value=None),
        patch("app.services.deploy.credentials.get_session") as mock_get_session,
        patch(
            "app.services.deploy.credentials.load_stored_vercel_token",
            new=AsyncMock(return_value="user-tok"),
        ),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)
        assert await has_deploy_credentials() is True


@pytest.mark.asyncio
async def test_has_deploy_credentials_false_when_none() -> None:
    with (
        patch("app.services.deploy.credentials.get_platform_vercel_token", return_value=None),
        patch("app.services.deploy.credentials.get_session") as mock_get_session,
        patch(
            "app.services.deploy.credentials.load_stored_vercel_token",
            new=AsyncMock(return_value=None),
        ),
    ):
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)
        assert await has_deploy_credentials() is False


@pytest.mark.asyncio
async def test_save_vercel_credentials_inserts_new_row() -> None:
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    with patch("app.services.deploy.credentials.get_encryption_service") as mock_service_factory:
        mock_service = mock_service_factory.return_value
        mock_service.encrypt_if_needed.return_value = ({"token": "saved-token"}, False)

        result = await save_vercel_credentials(mock_db, "saved-token")

    assert result["status"] == "success"
    mock_db.add.assert_called_once()
    added = mock_db.add.call_args.args[0]
    assert added.config_key == VERCEL_CREDENTIALS_KEY
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_vercel_credentials_updates_existing_row() -> None:
    mock_row = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = mock_row
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    with patch("app.services.deploy.credentials.get_encryption_service") as mock_service_factory:
        mock_service = mock_service_factory.return_value
        mock_service.encrypt_if_needed.return_value = ("cipher-blob", True)

        result = await save_vercel_credentials(mock_db, "updated-token")

    assert result["message"] == "Vercel credentials saved"
    assert mock_row.config_value == {"_cipher": "cipher-blob"}
    assert mock_row.is_encrypted is True
    mock_db.add.assert_not_called()
    mock_db.commit.assert_awaited_once()
