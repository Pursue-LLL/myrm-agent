"""Cross-issuer concurrent refresh must not lose updates.

Each issuer holds an independent refresh lock, but all issuers share the same
``oauthCredentials`` blob. Without a shared merge lock, two issuers refreshing
at the same time could overwrite each other's tokens. This test drives a real
DB with two issuers and asserts both refreshed tokens survive.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import UserConfig
from app.services.agent.oauth_refresher import _refresh_locks, refresh_oauth_token
from app.services.config.encryption import get_encryption_service

ISSUER_A = "mock-platform-a"
ISSUER_B = "mock-platform-b"

TOKEN_URL_A = "https://api.mockplatform-a.com/oauth/token"
TOKEN_URL_B = "https://api.mockplatform-b.com/oauth/token"


def _issuer_entry(issuer: str, token_url: str) -> dict[str, object]:
    return {
        "token": "old_token",
        "refresh_token": f"valid_refresh_{issuer}",
        "token_url": token_url,
        "client_id": f"client_{issuer}",
        "client_secret": f"secret_{issuer}",
        "user_id": f"user_{issuer}",
        "scope": "read_write",
        "expires_at": time.time() - 10,  # expired
    }


def _decrypt_blob(row: UserConfig) -> dict[str, object]:
    service = get_encryption_service()
    val = row.config_value
    if row.is_encrypted:
        if isinstance(val, str):
            val = service.decrypt(val)
        elif isinstance(val, dict) and "_cipher" in val:
            val = service.decrypt(val["_cipher"])
    return val if isinstance(val, dict) else {}


@pytest.fixture
async def setup_two_issuer_credentials():
    async with get_session() as db:
        await db.execute(delete(UserConfig).where(UserConfig.config_key == "oauthCredentials"))
        await db.commit()

        service = get_encryption_service()
        initial_creds = {
            ISSUER_A: _issuer_entry(ISSUER_A, TOKEN_URL_A),
            ISSUER_B: _issuer_entry(ISSUER_B, TOKEN_URL_B),
        }

        final_value: object = initial_creds
        is_encrypted = service.should_encrypt("oauthCredentials")
        if is_encrypted:
            enc_val, _ = service.encrypt_if_needed("oauthCredentials", initial_creds)
            final_value = {"_cipher": enc_val} if isinstance(enc_val, str) else enc_val

        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key="oauthCredentials",
                config_value=final_value,
                version="1.0.0",
                last_device_id="test_suite",
                is_encrypted=is_encrypted,
            )
        )
        await db.commit()

    _refresh_locks.clear()
    yield
    async with get_session() as db:
        await db.execute(delete(UserConfig).where(UserConfig.config_key == "oauthCredentials"))
        await db.commit()
    _refresh_locks.clear()


@pytest.mark.asyncio
async def test_concurrent_cross_issuer_refresh_preserves_both(setup_two_issuer_credentials):
    """Two issuers refreshing concurrently both keep their new tokens in the blob."""

    # Rendezvous barrier: both POST requests must have started before either
    # refresh proceeds to its write-back, so the two merges genuinely overlap.
    arrived = 0
    gate = asyncio.Event()

    async def _post(*args, **kwargs):
        nonlocal arrived
        await asyncio.sleep(0.4)
        arrived += 1
        if arrived == 2:
            gate.set()
        await gate.wait()
        data = kwargs.get("data") or {}
        refresh_token = str(data.get("refresh_token", ""))
        issuer = refresh_token.removeprefix("valid_refresh_")
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": f"fresh_{issuer}",
            "refresh_token": f"new_refresh_{issuer}",
            "expires_in": 3600,
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=_post):
        cred_a, cred_b = await asyncio.gather(
            refresh_oauth_token(ISSUER_A),
            refresh_oauth_token(ISSUER_B),
        )

    assert cred_a is not None and cred_b is not None
    assert cred_a.token == f"fresh_{ISSUER_A}"
    assert cred_b.token == f"fresh_{ISSUER_B}"

    async with get_session() as db:
        row = (
            await db.execute(select(UserConfig).where(UserConfig.config_key == "oauthCredentials"))
        ).scalars().first()
        assert row is not None

        val = _decrypt_blob(row)
        assert val[ISSUER_A]["token"] == f"fresh_{ISSUER_A}"
        assert val[ISSUER_B]["token"] == f"fresh_{ISSUER_B}"


@pytest.mark.asyncio
async def test_refresh_does_not_resurrect_disconnected_issuer(setup_two_issuer_credentials):
    """A disconnect during an in-flight refresh must not be resurrected by the write-back."""

    from app.services.integrations.oauth_store import delete_oauth_credential

    async def _post(*args, **kwargs):
        await asyncio.sleep(0.1)
        # User disconnects ISSUER_A while the refresh HTTP request is in flight.
        async with get_session() as db:
            await delete_oauth_credential(db, ISSUER_A)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": f"fresh_{ISSUER_A}",
            "refresh_token": f"new_refresh_{ISSUER_A}",
            "expires_in": 3600,
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=_post):
        cred = await refresh_oauth_token(ISSUER_A)

    # The in-flight session still returns the fresh token, but the disconnect
    # intent survives: ISSUER_A stays absent from the blob.
    assert cred is not None
    assert cred.token == f"fresh_{ISSUER_A}"

    async with get_session() as db:
        row = (
            await db.execute(select(UserConfig).where(UserConfig.config_key == "oauthCredentials"))
        ).scalars().first()
        assert row is not None

        val = _decrypt_blob(row)
        assert ISSUER_A not in val
        assert ISSUER_B in val
