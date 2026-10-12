"""API endpoint tests for Docker Sandbox 8-Flag Hardening and Host Vault-Proxy Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.docker_sandbox_hardening_router import (
    router as docker_sandbox_hardening_router,
)
from app.services.security.docker_sandbox_hardening_service import (
    DockerSandboxHardeningService,
)


@pytest.fixture
def client() -> TestClient:
    DockerSandboxHardeningService.reset_instance()
    app = FastAPI()
    app.include_router(docker_sandbox_hardening_router, prefix="/api/v1/security")
    return TestClient(app)


def test_build_and_verify_args_api(client: TestClient) -> None:
    # 1. Build hardened args
    resp_build = client.post(
        "/api/v1/security/docker-sandbox-hardening/build-args",
        json={
            "image": "python:3.12-alpine",
            "command": ["python", "app.py"],
            "config": {
                "read_only": True,
                "tmp_size_mb": 100,
                "tmp_noexec": True,
                "pids_limit": 100,
                "cap_drop_all": True,
                "no_new_privileges": True,
                "user": "1000:1000",
                "network_mode": "none",
                "memory_limit": "512m",
                "cpus_quota": 1.0,
                "auto_remove": True,
            },
        },
    )
    assert resp_build.status_code == 200
    data_build = resp_build.json()
    assert data_build["flags_verified"]
    raw_args: list[str] = data_build["raw_args"]
    assert "--read-only" in raw_args
    assert "--tmpfs=/tmp:size=100m,noexec" in raw_args
    assert "--pids-limit=100" in raw_args

    # 2. Verify flags on the built args
    resp_verify = client.post(
        "/api/v1/security/docker-sandbox-hardening/verify-flags",
        json={"raw_args": raw_args},
    )
    assert resp_verify.status_code == 200
    assert resp_verify.json()["flags_verified"]


def test_check_env_leak_api(client: TestClient) -> None:
    # Leaky env
    resp_leaky = client.post(
        "/api/v1/security/docker-sandbox-hardening/check-env-leak",
        json={
            "env_args": [
                "-e",
                "GITHUB_TOKEN=ghp_testleak123456",
                "--env",
                "STRIPE_API_KEY=sk_test_key",
            ]
        },
    )
    assert resp_leaky.status_code == 200
    data_leaky = resp_leaky.json()
    assert not data_leaky["is_safe"]
    assert len(data_leaky["detected_leaks"]) == 2

    # Safe env
    resp_safe = client.post(
        "/api/v1/security/docker-sandbox-hardening/check-env-leak",
        json={"env_args": ["-e", "ENV=test"]},
    )
    assert resp_safe.status_code == 200
    assert resp_safe.json()["is_safe"]


def test_vault_credentials_and_relay_api(client: TestClient) -> None:
    # 1. Register credential
    resp_reg = client.post(
        "/api/v1/security/docker-sandbox-hardening/vault/credentials",
        json={
            "credential_id": "cred_aws_s3",
            "target_service": "AWS S3",
            "secret_value": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "allowed_domains": ["s3.amazonaws.com"],
            "description": "S3 sync bucket",
        },
    )
    assert resp_reg.status_code == 201
    assert resp_reg.json()["secret_value"] == "[REDACTED_IN_VAULT]"

    # 2. List credentials
    resp_list = client.get("/api/v1/security/docker-sandbox-hardening/vault/credentials")
    assert resp_list.status_code == 200
    creds = resp_list.json()
    assert len(creds) == 1
    assert creds[0]["credential_id"] == "cred_aws_s3"

    # 3. Relay outbound allowed
    resp_relay_ok = client.post(
        "/api/v1/security/docker-sandbox-hardening/vault/relay",
        json={
            "project_id": "proj_demo",
            "target_url": "https://s3.amazonaws.com/my-bucket/data.csv",
            "credential_id": "cred_aws_s3",
        },
    )
    assert resp_relay_ok.status_code == 200
    assert resp_relay_ok.json()["credential_injected"]

    # 4. Relay outbound blocked (domain not in allowlist)
    resp_relay_blocked = client.post(
        "/api/v1/security/docker-sandbox-hardening/vault/relay",
        json={
            "project_id": "proj_demo",
            "target_url": "https://evil-exfiltration.com/data.csv",
            "credential_id": "cred_aws_s3",
        },
    )
    assert resp_relay_blocked.status_code == 200
    assert resp_relay_blocked.json()["status_code"] == 403
    assert not resp_relay_blocked.json()["credential_injected"]


def test_lazy_lifecycle_api(client: TestClient) -> None:
    # 1. Check initial status
    resp_stat = client.get("/api/v1/security/docker-sandbox-hardening/lifecycle/status")
    assert resp_stat.status_code == 200
    assert resp_stat.json()["status"] == "uninitialized"

    # 2. Provision dynamically
    resp_prov = client.post("/api/v1/security/docker-sandbox-hardening/lifecycle/provision")
    assert resp_prov.status_code == 200
    assert resp_prov.json()["status"] == "running"
    assert resp_prov.json()["container_id"] is not None

    # 3. Dispose
    resp_disp = client.post("/api/v1/security/docker-sandbox-hardening/lifecycle/dispose")
    assert resp_disp.status_code == 200
    assert resp_disp.json()["status"] == "disposed"
