"""
[POS] tests/api/security/test_vnc_hardening_endpoints.py
[INPUT] app.api.security.vnc_hardening_router, app.services.security.vnc_hardening_service
[OUTPUT] Integration tests for VNC Loopback Bind & Rfbauth Hardening REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.vnc_hardening_router import router as vnc_hardening_router
from app.services.security.vnc_hardening_service import (
    VncHardeningService,
    get_vnc_hardening_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = VncHardeningService()
    app = FastAPI()
    app.include_router(vnc_hardening_router)
    app.dependency_overrides[get_vnc_hardening_service] = lambda: service
    return TestClient(app)


def test_endpoint_sanitize_default_config(client: TestClient) -> None:
    resp = client.post(
        "/vnc-hardening/sanitize",
        json={
            "display_num": 0,
            "vnc_port": 5900,
            "passwd_file": "/tmp/vnc_pass",
            "bind_mode": "loopback",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_hardened"] is True
    assert data["effective_bind_mode"] == "loopback"
    assert "-localhost" in data["command_args"]
    assert "-nopw" not in data["command_args"]
    assert "-rfbauth" in data["command_args"]
    assert "/tmp/vnc_pass" in data["command_args"]


def test_endpoint_sanitize_auto_remediate_and_strict_error(client: TestClient) -> None:
    # 1. auto_remediate=True -> 200 with stripped flag
    resp_remediated = client.post(
        "/vnc-hardening/sanitize",
        json={
            "display_num": 1,
            "vnc_port": 5901,
            "passwd_file": "/tmp/vnc_pass",
            "extra_flags": ["-nopw"],
            "auto_remediate": True,
        },
    )
    assert resp_remediated.status_code == 200
    data_rem = resp_remediated.json()
    assert "-nopw" not in data_rem["command_args"]
    assert len(data_rem["violations"]) == 1
    assert data_rem["violations"][0]["violation_type"] == "nopw_conflict"

    # 2. auto_remediate=False -> 400 Bad Request
    resp_strict = client.post(
        "/vnc-hardening/sanitize",
        json={
            "display_num": 1,
            "vnc_port": 5901,
            "passwd_file": "/tmp/vnc_pass",
            "extra_flags": ["-nopw"],
            "auto_remediate": False,
        },
    )
    assert resp_strict.status_code == 400
    assert "Conflicting '-nopw' flag detected" in resp_strict.json()["detail"]


def test_endpoint_audit_raw_command(client: TestClient) -> None:
    # Insecure invocation
    resp_insecure = client.post(
        "/vnc-hardening/audit",
        json={"command_args": ["x11vnc", "-display", ":0", "-nopw"]},
    )
    assert resp_insecure.status_code == 200
    data_insecure = resp_insecure.json()
    assert data_insecure["verdict"] == "BLOCKED"
    assert len(data_insecure["remediation_summary"]) > 0

    # Compliant invocation
    resp_compliant = client.post(
        "/vnc-hardening/audit",
        json={
            "command_args": [
                "x11vnc",
                "-display",
                ":0",
                "-rfbauth",
                "/tmp/pass",
                "-localhost",
            ]
        },
    )
    assert resp_compliant.status_code == 200
    data_compliant = resp_compliant.json()
    assert data_compliant["verdict"] == "PASS"


def test_endpoint_password_management(client: TestClient) -> None:
    # Generate password
    gen_resp = client.post(
        "/vnc-hardening/generate-password",
        json={"length": 16},
    )
    assert gen_resp.status_code == 200
    pwd = gen_resp.json()["password"]
    assert len(pwd) == 16

    # Evaluate strong password
    eval_strong = client.post(
        "/vnc-hardening/evaluate-password",
        json={"password": pwd},
    )
    assert eval_strong.status_code == 200
    assert eval_strong.json()["is_valid"] is True

    # Evaluate weak password
    eval_weak = client.post(
        "/vnc-hardening/evaluate-password",
        json={"password": "123"},
    )
    assert eval_weak.status_code == 200
    assert eval_weak.json()["is_valid"] is False
