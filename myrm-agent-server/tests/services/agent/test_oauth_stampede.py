from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import UserConfig
from app.services.agent.oauth_refresher import _refresh_locks, refresh_oauth_token
from app.services.config.encryption import get_encryption_service


@pytest.fixture
async def setup_oauth_credentials():
    async with get_session() as db:
        # Clean any old config
        await db.execute(delete(UserConfig).where(UserConfig.config_key == "oauthCredentials"))
        await db.commit()

        service = get_encryption_service()
        initial_creds = {
            "mock-platform": {
                "token": "old_token",
                "refresh_token": "valid_refresh",
                "token_url": "https://api.mockplatform.com/oauth/token",
                "client_id": "client123",
                "client_secret": "secret123",
                "user_id": "user123",
                "scope": "read_write",
                "expires_at": time.time() - 10,  # expired
            }
        }

        # Check encryption
        is_encrypted = service.should_encrypt("oauthCredentials")
        final_value = initial_creds
        if is_encrypted:
            enc_val, _ = service.encrypt_if_needed("oauthCredentials", initial_creds)
            if isinstance(enc_val, str):
                final_value = {"_cipher": enc_val}
            else:
                final_value = enc_val

        import uuid

        row = UserConfig(
            id=str(uuid.uuid4()),
            config_key="oauthCredentials",
            config_value=final_value,
            version="1.0.0",
            last_device_id="test_suite",
            is_encrypted=is_encrypted,
        )
        db.add(row)
        await db.commit()

    _refresh_locks.clear()
    yield "mock-platform"

    # Cleanup
    async with get_session() as db:
        await db.execute(delete(UserConfig).where(UserConfig.config_key == "oauthCredentials"))
        await db.commit()
    _refresh_locks.clear()


@pytest.mark.asyncio
async def test_oauth_stampede_concurrency_lock(setup_oauth_credentials):
    issuer = setup_oauth_credentials

    # We mock the HTTP client's POST method
    # When called, it should sleep briefly to allow parallel stampede requests to queue up on the lock
    mock_post_calls = 0

    async def mock_post(*args, **kwargs):
        nonlocal mock_post_calls
        current_num = mock_post_calls + 1
        mock_post_calls += 1
        await asyncio.sleep(0.4)  # artificial delay

        # Return mock HTTPX response
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": f"fresh_token_after_{current_num}",
            "refresh_token": f"new_refresh_{current_num}",
            "expires_in": 3600,
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        # Fire 5 concurrent refresh requests
        results = await asyncio.gather(*(refresh_oauth_token(issuer) for _ in range(5)))

        # Assertions
        # 1. Verify that httpx.AsyncClient.post was called EXACTLY ONCE
        assert mock_post_calls == 1

        # 2. Verify all results are valid EphemeralUserCredential instances
        assert len(results) == 5
        for cred in results:
            assert cred is not None
            # 3. Verify all 5 callers received the exact same first refreshed token
            # (due to the double-checked locking, subsequent callers skip HTTP and read the DB)
            assert cred.token == "fresh_token_after_1"
            assert cred.issuer == "mock-platform"
            assert cred.scope == "read_write"
            assert cred.user_id == "user123"

        # 4. Read the DB to verify that the final persisted state has the same token
        async with get_session() as db:
            row = (await db.execute(select(UserConfig).where(UserConfig.config_key == "oauthCredentials"))).scalars().first()
            assert row is not None

            service = get_encryption_service()
            val = row.config_value
            if row.is_encrypted:
                if isinstance(val, str):
                    val = service.decrypt(val)
                elif isinstance(val, dict) and "_cipher" in val:
                    val = service.decrypt(val["_cipher"])

            assert val["mock-platform"]["token"] == "fresh_token_after_1"
            assert val["mock-platform"]["refresh_token"] == "new_refresh_1"
            assert val["mock-platform"]["expires_at"] > time.time() + 3000
