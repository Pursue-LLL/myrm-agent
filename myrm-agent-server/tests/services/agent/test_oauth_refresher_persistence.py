"""Tests for OAuth refresher write-path persistence of the is_encrypted flag.

The refresher must keep ``is_encrypted`` in sync with the value returned by
``encrypt_if_needed``; otherwise a re-encrypted token would be read as
plaintext on the next access.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.models import UserConfig


class _MockResponse:
    status_code = 200

    def json(self) -> dict[str, object]:
        return {"access_token": "new-token", "expires_in": 3600}


def _build_row(is_encrypted: bool) -> UserConfig:
    return UserConfig(
        id="row-id",
        config_key="oauthCredentials",
        config_value={
            "test_issuer": {
                "refresh_token": "rt",
                "token_url": "https://t.example.com",
                "expires_at": 0,
            }
        },
        version="1.0.0",
        last_device_id="sandbox",
        is_encrypted=is_encrypted,
    )


async def _run_refresh(service: MagicMock) -> tuple[UserConfig, MagicMock]:
    from app.services.agent import oauth_refresher

    row = _build_row(is_encrypted=True)

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

        result = await refresh_oauth_token("test_issuer")

    assert result is not None
    return row, mock_session


@pytest.mark.asyncio
async def test_refresh_persists_is_encrypted_true() -> None:
    """When encrypt_if_needed encrypts, the persisted row must be marked encrypted."""
    service = MagicMock()
    service.encrypt_if_needed = MagicMock(return_value=("cipher-payload", True))

    row, _ = await _run_refresh(service)

    assert row.is_encrypted is True
    assert row.config_value == {"_cipher": "cipher-payload"}


@pytest.mark.asyncio
async def test_refresh_persists_is_encrypted_false_when_not_sensitive() -> None:
    """When the key is not sensitive, the plaintext payload must keep is_encrypted False."""
    service = MagicMock()
    payload = {"issuer": {"token": "plain"}}
    service.encrypt_if_needed = MagicMock(return_value=(payload, False))

    row, _ = await _run_refresh(service)

    assert row.is_encrypted is False
    assert row.config_value == payload
