"""Tests for OAuth refresher write-path persistence of the is_encrypted flag.

The refresher must keep ``is_encrypted`` in sync with the value returned by
``encrypt_if_needed``; otherwise a re-encrypted token would be read as
plaintext on the next access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import UserConfig


def _make_token_dict() -> dict[str, object]:
    return {
        "test_issuer": {
            "refresh_token": "rt",
            "token_url": "https://t.example.com",
            "expires_at": 0,
        }
    }


class _MockResponse:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {"access_token": "new-token", "expires_in": 3600}


async def _run_refresh(
    *,
    row_config_value: object,
    row_is_encrypted: bool,
    encrypt_result: tuple[object, bool],
) -> tuple[UserConfig, MagicMock]:
    from app.services.agent import oauth_refresher

    row = UserConfig(
        id="row-id",
        config_key="oauthCredentials",
        config_value=row_config_value,
        version="1.0.0",
        last_device_id="sandbox",
        is_encrypted=row_is_encrypted,
    )

    service = MagicMock()
    service.decrypt = MagicMock(return_value=_make_token_dict())
    service.encrypt_if_needed = MagicMock(return_value=encrypt_result)

    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = row

    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=_MockResponse())
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with (
        patch.object(oauth_refresher, "get_session", return_value=mock_session),
        patch.object(oauth_refresher, "get_encryption_service", return_value=service),
        patch.object(oauth_refresher, "httpx") as mock_httpx,
        patch.object(oauth_refresher, "flag_modified"),
    ):
        mock_httpx.AsyncClient.return_value = mock_client
        from app.services.agent.oauth_refresher import refresh_oauth_token

        await refresh_oauth_token("test_issuer")

    return row, service


@pytest.mark.asyncio
async def test_refresh_reencrypts_and_persists_flag() -> None:
    """An already-encrypted row stays encrypted after a refresh."""
    row, service = await _run_refresh(
        row_config_value={"_cipher": "old-cipher"},
        row_is_encrypted=True,
        encrypt_result=("new-cipher", True),
    )

    service.decrypt.assert_called_once_with("old-cipher")
    assert row.is_encrypted is True
    assert row.config_value == {"_cipher": "new-cipher"}


@pytest.mark.asyncio
async def test_refresh_upgrades_legacy_plaintext_to_encrypted() -> None:
    """A legacy plaintext row (pre-sensitive-key) becomes encrypted on refresh."""
    row, service = await _run_refresh(
        row_config_value=_make_token_dict(),
        row_is_encrypted=False,
        encrypt_result=("fresh-cipher", True),
    )

    service.decrypt.assert_not_called()
    assert row.is_encrypted is True
    assert row.config_value == {"_cipher": "fresh-cipher"}


@pytest.mark.asyncio
async def test_refresh_keeps_flag_false_when_not_encrypting() -> None:
    """When the policy returns plaintext, the flag must not be stuck True."""
    row, _ = await _run_refresh(
        row_config_value=_make_token_dict(),
        row_is_encrypted=True,
        encrypt_result=(_make_token_dict(), False),
    )

    assert row.is_encrypted is False
    assert row.config_value == _make_token_dict()
