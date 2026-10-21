"""Unit tests for remote-access E2EE crypto and handshake."""

from __future__ import annotations

import pytest

from app.remote_access.e2ee import (
    decrypt_utf8,
    encrypt_utf8,
    generate_keypair,
    get_e2ee_session_store,
    public_key_b64,
)


@pytest.mark.asyncio
async def test_box_roundtrip() -> None:
    alice_pub, alice_sec = generate_keypair()
    bob_pub, bob_sec = generate_keypair()
    message = "pair-token-secret-123"
    cipher = encrypt_utf8(secret_key=alice_sec, peer_public_key=bob_pub, text=message)
    plain = decrypt_utf8(secret_key=bob_sec, peer_public_key=alice_pub, bundle_b64=cipher)
    assert plain == message


@pytest.mark.asyncio
async def test_handshake_creates_session() -> None:
    client_pub, client_sec = generate_keypair()
    daemon_pub, daemon_sec = generate_keypair()
    store = get_e2ee_session_store()
    session = await store.create_from_hello(
        client_public_key_b64=public_key_b64(client_pub),
        daemon_secret_key=daemon_sec,
    )
    assert session.session_id
    cipher = session.encrypt_text('{"hello":"mobile"}')
    plain = decrypt_utf8(
        secret_key=client_sec,
        peer_public_key=daemon_pub,
        bundle_b64=cipher,
    )
    assert plain == '{"hello":"mobile"}'
