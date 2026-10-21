"""Integration tests for E2EE handshake HTTP API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.remote_access.e2ee import generate_keypair, public_key_b64
from tests.support.minimal_app import build_minimal_app


def test_e2ee_public_key_and_handshake() -> None:
    app = build_minimal_app("remote_access")
    with TestClient(app) as client:
        pub_resp = client.get("/api/v1/remote-access/e2ee/public-key")
        assert pub_resp.status_code == 200
        pub_payload = pub_resp.json()
        assert pub_payload["data"]["publicKeyB64"]

        client_pub, _client_sec = generate_keypair()
        hello_resp = client.post(
            "/api/v1/remote-access/e2ee/handshake",
            json={"type": "e2ee_hello", "key": public_key_b64(client_pub)},
        )
        assert hello_resp.status_code == 200
        hello_payload = hello_resp.json()
        assert hello_payload["data"]["type"] == "e2ee_ready"
        assert hello_payload["data"]["sessionId"]
