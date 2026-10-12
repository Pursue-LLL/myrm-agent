"""Unit tests for DockerSandboxHardeningService."""

import pytest

from app.schemas.docker_sandbox_hardening import (
    BuildRunArgsRequest,
    CheckEnvLeakRequest,
    EightFlagConfigRequest,
    NetworkIsolationEnum,
    ProvisionStatusEnum,
    RegisterVaultCredentialRequest,
    VaultProxyRelayRequest,
    VerifyFlagsRequest,
)
from app.services.security.docker_sandbox_hardening_service import (
    DockerSandboxHardeningService,
)


@pytest.fixture(autouse=True)
def clean_service() -> None:
    DockerSandboxHardeningService.reset_instance()


def test_service_build_and_verify_args() -> None:
    service = DockerSandboxHardeningService.get_instance()

    req = BuildRunArgsRequest(
        image="ghcr.io/myrm-ai/sandbox-node:20",
        command=["npm", "test"],
        config=EightFlagConfigRequest(
            read_only=True,
            tmp_size_mb=100,
            tmp_noexec=True,
            pids_limit=100,
            cap_drop_all=True,
            no_new_privileges=True,
            user="1000:1000",
            network_mode=NetworkIsolationEnum.NONE,
            memory_limit="512m",
            cpus_quota=1.0,
            auto_remove=True,
        ),
    )
    resp = service.build_run_args(req)
    assert resp.flags_verified
    assert len(resp.missing_flags) == 0
    assert "--read-only" in resp.raw_args
    assert "--pids-limit=100" in resp.raw_args
    assert "--tmpfs=/tmp:size=100m,noexec" in resp.raw_args

    # Verify arbitrary args
    verify_resp = service.verify_flags(VerifyFlagsRequest(raw_args=resp.raw_args))
    assert verify_resp.flags_verified

    # Missing flags audit
    incomplete_verify = service.verify_flags(
        VerifyFlagsRequest(raw_args=["docker", "run", "alpine"])
    )
    assert not incomplete_verify.flags_verified
    assert "FLAG_1_READ_ONLY" in incomplete_verify.missing_flags


def test_service_check_env_leak() -> None:
    service = DockerSandboxHardeningService.get_instance()

    # Leaking case
    leak_resp = service.check_env_leak(
        CheckEnvLeakRequest(
            env_args=[
                "-e",
                "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE",
                "--env",
                "OPENAI_API_KEY=sk-abcdef",
            ]
        )
    )
    assert not leak_resp.is_safe
    assert len(leak_resp.detected_leaks) == 2

    # Safe case
    safe_resp = service.check_env_leak(
        CheckEnvLeakRequest(
            env_args=["-e", "NODE_ENV=production", "--env", "PORT=8080"]
        )
    )
    assert safe_resp.is_safe
    assert len(safe_resp.detected_leaks) == 0


def test_service_vault_credentials_and_relay() -> None:
    service = DockerSandboxHardeningService.get_instance()

    # Register
    reg_resp = service.register_credential(
        RegisterVaultCredentialRequest(
            credential_id="cred_npm_token",
            target_service="NPM Registry",
            secret_value="npm_secret_auth_token_xyz",
            allowed_domains=["registry.npmjs.org"],
            description="NPM publish credentials",
        )
    )
    assert reg_resp.secret_value == "[REDACTED_IN_VAULT]"
    assert reg_resp.allowed_domains == ["registry.npmjs.org"]

    # List
    creds_list = service.list_credentials()
    assert len(creds_list) == 1
    assert creds_list[0].secret_value == "[REDACTED_IN_VAULT]"

    # Relay with permitted domain
    relay_ok = service.relay_outbound_request(
        VaultProxyRelayRequest(
            project_id="proj_1",
            target_url="https://registry.npmjs.org/packages",
            credential_id="cred_npm_token",
        )
    )
    assert relay_ok.status_code == 200
    assert relay_ok.credential_injected
    assert relay_ok.blocked_reason is None

    # Relay with forbidden domain
    relay_blocked = service.relay_outbound_request(
        VaultProxyRelayRequest(
            project_id="proj_1",
            target_url="https://attacker-controlled.site/steal",
            credential_id="cred_npm_token",
        )
    )
    assert relay_blocked.status_code == 403
    assert not relay_blocked.credential_injected
    assert "not permitted" in (relay_blocked.blocked_reason or "")


def test_service_lazy_lifecycle() -> None:
    service = DockerSandboxHardeningService.get_instance()

    # Initial status
    stat1 = service.get_lifecycle_status()
    assert stat1.status == ProvisionStatusEnum.UNINITIALIZED
    assert stat1.container_id is None

    # Lazy provision
    prov_resp = service.ensure_provisioned(image="ghcr.io/myrm-ai/sandbox-runtime:latest")
    assert prov_resp.status == ProvisionStatusEnum.RUNNING
    assert prov_resp.container_id is not None
    assert prov_resp.flags_verified

    # Dispose
    disp_resp = service.dispose_sandbox()
    assert disp_resp.status == ProvisionStatusEnum.DISPOSED
    assert disp_resp.container_id is None
