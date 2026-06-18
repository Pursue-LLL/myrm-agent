"""Unit tests for E2EE session store capacity and pruning."""

from __future__ import annotations

import pytest

from app.remote_access.e2ee_crypto import generate_keypair, public_key_b64
from app.remote_access.e2ee_session import E2EE_MAX_SESSIONS, E2EESessionStore


@pytest.mark.asyncio
async def test_session_store_evicts_oldest_when_at_capacity() -> None:
    store = E2EESessionStore()
    _, daemon_sec = generate_keypair()
    created_ids: list[str] = []

    for _ in range(E2EE_MAX_SESSIONS + 1):
        client_pub, _ = generate_keypair()
        session = await store.create_from_hello(
            client_public_key_b64=public_key_b64(client_pub),
            daemon_secret_key=daemon_sec,
        )
        created_ids.append(session.session_id)

    oldest_id = created_ids[0]
    assert await store.get(oldest_id) is None
    assert await store.get(created_ids[-1]) is not None
