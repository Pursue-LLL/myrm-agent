"""Tests for E2EE middleware session sliding refresh."""

from __future__ import annotations

import time

import pytest

from app.remote_access.e2ee import generate_keypair, get_e2ee_session_store, public_key_b64


@pytest.mark.asyncio
async def test_e2ee_session_refresh_extends_expiry() -> None:
    store = get_e2ee_session_store()
    client_pub, _ = generate_keypair()
    _, daemon_sec = generate_keypair()
    session = await store.create_from_hello(
        client_public_key_b64=public_key_b64(client_pub),
        daemon_secret_key=daemon_sec,
        ttl_seconds=60,
    )
    original_expires = session.expires_at
    time.sleep(0.01)
    await store.refresh(session.session_id)
    refreshed = await store.get(session.session_id)
    assert refreshed is not None
    assert refreshed.expires_at > original_expires
