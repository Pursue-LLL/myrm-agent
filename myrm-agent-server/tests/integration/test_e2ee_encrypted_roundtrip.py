"""Integration tests for encrypted mobile remote API and SSE frames."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config.deploy_mode import get_deploy_mode
from app.config.settings import settings
from tests.support.minimal_app import build_minimal_app

from app.remote_access.e2ee import (
    E2EE_PAIR_CIPHERTEXT_HEADER,
    E2EE_SESSION_HEADER,
    decrypt_utf8,
    encrypt_sse_stream,
    encrypt_utf8,
    generate_keypair,
    get_e2ee_session_store,
    load_or_create_daemon_keypair,
    public_key_b64,
)
from app.remote_access.pairing import MOBILE_HUB_LIST_PURPOSE, create_pairing_token

_REMOTE_HEADERS = {"Host": "abc.trycloudflare.com"}


@pytest.fixture(autouse=True)
def _local_remote_webui(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOY_MODE", "local")
    monkeypatch.setenv("WEBUI_MODE", "true")
    monkeypatch.setenv("WEBUI_REMOTE_MODE", "true")
    monkeypatch.setattr(settings.database, "state_dir", str(tmp_path))
    get_deploy_mode.cache_clear()
    from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

    _reset_capabilities_cache_for_testing()
    yield
    get_deploy_mode.cache_clear()
    _reset_capabilities_cache_for_testing()


def _handshake_session(client: TestClient) -> tuple[str, bytes, bytes]:
    client_pub, client_sec = generate_keypair()
    hello_resp = client.post(
        "/api/v1/remote-access/e2ee/handshake",
        json={"type": "e2ee_hello", "key": public_key_b64(client_pub)},
    )
    assert hello_resp.status_code == 200
    session_id = hello_resp.json()["data"]["sessionId"]
    daemon_keypair = load_or_create_daemon_keypair()
    return session_id, client_sec, daemon_keypair.public_key


def test_e2ee_encrypted_mobile_sessions_roundtrip() -> None:
    pair_token = create_pairing_token(chat_id=None, purpose=MOBILE_HUB_LIST_PURPOSE)
    app = build_minimal_app("remote_access")
    with TestClient(app) as client:
        session_id, client_sec, daemon_pub = _handshake_session(client)
        encrypted_pair = encrypt_utf8(
            secret_key=client_sec,
            peer_public_key=daemon_pub,
            text=pair_token,
        )
        response = client.get(
            "/api/v1/remote-access/mobile/sessions",
            headers={
                **_REMOTE_HEADERS,
                E2EE_SESSION_HEADER: session_id,
                E2EE_PAIR_CIPHERTEXT_HEADER: encrypted_pair,
            },
        )
        assert response.status_code == 200
        body = response.json()
        if isinstance(body.get("c"), str):
            plain = decrypt_utf8(
                secret_key=client_sec,
                peer_public_key=daemon_pub,
                bundle_b64=body["c"],
            )
            payload = json.loads(plain)
        else:
            payload = body
        assert payload["success"] is True
        assert "activeSessions" in payload["data"]


@pytest.mark.asyncio
async def test_e2ee_sse_frame_roundtrip() -> None:
    client_pub, client_sec = generate_keypair()
    daemon_keypair = load_or_create_daemon_keypair()
    session = await get_e2ee_session_store().create_from_hello(
        client_public_key_b64=public_key_b64(client_pub),
        daemon_secret_key=daemon_keypair.secret_key,
    )
    plain_chunk = 'data: {"type":"ping","data":{}}\n\n'

    async def source():
        yield plain_chunk

    encrypted_frames: list[str] = []
    async for frame in encrypt_sse_stream(source(), session):
        encrypted_frames.append(frame)

    assert len(encrypted_frames) == 1
    frame = encrypted_frames[0]
    assert frame.startswith("event: e2ee_frame\n")
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: ").strip())
    cipher = payload["c"]
    decrypted = decrypt_utf8(
        secret_key=client_sec,
        peer_public_key=daemon_keypair.public_key,
        bundle_b64=cipher,
    )
    assert decrypted == plain_chunk
