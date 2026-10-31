"""Unit and integration tests for SSH Vault read-only gate, change window, and break-glass tokens.

[INPUT]
- pytest
- httpx::AsyncClient
- app.services.ssh_vault::SSHAssetService, SSHHostConfig, ProtectedChangeWindowService
- tests.services.ssh_vault.conftest::StandInSsh (a program named `ssh` that never connects)

[OUTPUT]
- Test suite verifying read-only enforcement, single-use break-glass token lifecycle, policy APIs, and that no copy of a command or full token is retained or logged

[POS]
Unit & integration tests in tests/services/ssh_vault/.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.ssh_vault.change_window import ProtectedChangeWindowService
from app.services.ssh_vault.models import SSHHostConfig
from app.services.ssh_vault.service import SSHAssetService, get_ssh_asset_service

if TYPE_CHECKING:
    from tests.services.ssh_vault.conftest import StandInSsh


@pytest.fixture
def change_window_service() -> ProtectedChangeWindowService:
    return ProtectedChangeWindowService()


@pytest.fixture
def vault_service(change_window_service: ProtectedChangeWindowService) -> SSHAssetService:
    service = SSHAssetService(change_window_service=change_window_service)
    # Register test hosts
    prod_host = SSHHostConfig(
        host_alias="prod-server-01",
        hostname="10.0.1.10",
        port=22,
        user="deploy",
        is_read_only=True,
        environment_tier="production",
        require_confirm_on_write=True,
    )
    dev_host = SSHHostConfig(
        host_alias="dev-server-01",
        hostname="10.0.2.20",
        port=22,
        user="dev",
        is_read_only=False,
        environment_tier="development",
    )
    service.register_host(prod_host)
    service.register_host(dev_host)
    return service


def test_break_glass_token_issuance_and_single_use(change_window_service: ProtectedChangeWindowService) -> None:
    token_data = change_window_service.issue_break_glass_token(
        host_alias="prod-server-01",
        command="systemctl restart nginx",
        reason="Emergency certificate renewal",
        ttl_seconds=300,
    )
    assert token_data.token.startswith("bg_")
    assert token_data.consumed is False
    assert token_data.host_alias == "prod-server-01"

    # First consumption succeeds
    is_valid, err = change_window_service.verify_and_consume_token(
        token=token_data.token,
        host_alias="prod-server-01",
        command="systemctl restart nginx",
    )
    assert is_valid is True
    assert err == ""

    # Second consumption fails (replay attack prevention)
    is_valid2, err2 = change_window_service.verify_and_consume_token(
        token=token_data.token,
        host_alias="prod-server-01",
        command="systemctl restart nginx",
    )
    assert is_valid2 is False
    assert "already been consumed" in err2


def test_break_glass_tamper_and_mismatch_protection(change_window_service: ProtectedChangeWindowService) -> None:
    token_data = change_window_service.issue_break_glass_token(
        host_alias="prod-server-01",
        command="apt update",
        reason="Security patch",
        ttl_seconds=300,
    )

    # Command tampered
    is_valid, err = change_window_service.verify_and_consume_token(
        token=token_data.token,
        host_alias="prod-server-01",
        command="apt update && rm -rf /var/log",
    )
    assert is_valid is False
    assert "command mismatch" in err

    # Host mismatch
    is_valid_host, err_host = change_window_service.verify_and_consume_token(
        token=token_data.token,
        host_alias="other-host",
        command="apt update",
    )
    assert is_valid_host is False
    assert "bound to host" in err_host


def test_break_glass_token_expiration(change_window_service: ProtectedChangeWindowService) -> None:
    token_data = change_window_service.issue_break_glass_token(
        host_alias="prod-server-01",
        command="systemctl reload nginx",
        reason="Reload config",
        ttl_seconds=1,  # 1 second TTL
    )
    time.sleep(1.1)

    is_valid, err = change_window_service.verify_and_consume_token(
        token=token_data.token,
        host_alias="prod-server-01",
        command="systemctl reload nginx",
    )
    assert is_valid is False
    assert "expired" in err


@pytest.mark.asyncio
async def test_vault_service_read_only_blocking_and_break_glass(vault_service: SSHAssetService, stand_in_ssh: StandInSsh) -> None:
    # 1. State-mutating command on read-only host is blocked
    res = await vault_service.execute_remote_command(
        host_alias="prod-server-01",
        command="systemctl restart nginx",
    )
    assert res.exit_code == 126
    assert res.is_read_only_violation is True
    assert res.break_glass_token_used is False
    assert "Read-only security gate blocked" in res.stderr

    # 2. Issue break-glass token and authorize write execution
    token_data = vault_service.change_window.issue_break_glass_token(
        host_alias="prod-server-01",
        command="systemctl restart nginx",
        reason="Fix crash",
    )

    stand_in_ssh.print_and_exit(stdout="nginx restarted\n")
    res_authorized = await vault_service.execute_remote_command(
        host_alias="prod-server-01",
        command="systemctl restart nginx",
        break_glass_token=token_data.token,
    )
    assert res_authorized.exit_code == 0
    assert res_authorized.break_glass_token_used is True
    assert res_authorized.is_read_only_violation is False
    assert "nginx restarted" in res_authorized.stdout

    # 3. Read-only command executes without break-glass token
    stand_in_ssh.print_and_exit(stdout="Active: active (running)\n")
    res_ro = await vault_service.execute_remote_command(
        host_alias="prod-server-01",
        command="systemctl status nginx",
    )
    assert res_ro.exit_code == 0
    assert res_ro.is_read_only_violation is False
    assert res_ro.break_glass_token_used is False


@pytest.mark.asyncio
async def test_api_break_glass_flow() -> None:
    from fastapi import FastAPI

    from app.api.ssh_vault.router import router as ssh_vault_router

    vault_app = FastAPI()
    vault_app.include_router(ssh_vault_router)
    transport = ASGITransport(app=vault_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register or ensure test host exists
        global_service = get_ssh_asset_service()
        global_service.register_host(
            SSHHostConfig(
                host_alias="api-prod-host",
                hostname="127.0.0.1",
                is_read_only=True,
                environment_tier="production",
            )
        )

        # 2. Attempt write execution without token -> blocked
        res_blocked = await client.post(
            "/ssh-vault/execute",
            json={
                "host_alias": "api-prod-host",
                "command": "systemctl restart app",
            },
        )
        assert res_blocked.status_code == 200
        data_blocked = res_blocked.json()
        assert data_blocked["exit_code"] == 126
        assert data_blocked["is_read_only_violation"] is True

        # 3. Request break glass token
        res_bg = await client.post(
            "/ssh-vault/break-glass/request",
            json={
                "host_alias": "api-prod-host",
                "command": "systemctl restart app",
                "reason": "Hotfix deployment",
                "ttl_seconds": 300,
            },
        )
        assert res_bg.status_code == 200
        bg_data = res_bg.json()
        token = bg_data["token"]
        assert token.startswith("bg_")

        # 4. Update policy to read-write
        res_patch = await client.patch(
            "/ssh-vault/host/api-prod-host/policy",
            json={"is_read_only": False, "environment_tier": "staging"},
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_a_blocked_high_risk_command_is_logged_masked(
    vault_service: SSHAssetService, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    result = await vault_service.execute_remote_command(host_alias="dev-server-01", command="rm -rf /tmp/build --key abc123xyz")
    assert result.is_blocked_high_risk
    assert "Blocked high-risk command" in caplog.text
    assert "abc123xyz" not in caplog.text


@pytest.mark.asyncio
async def test_a_read_only_violation_is_logged_masked(vault_service: SSHAssetService, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    await vault_service.execute_remote_command(host_alias="prod-server-01", command="touch /tmp/flag --key abc123xyz")
    assert "Blocked read-only violation" in caplog.text
    assert "abc123xyz" not in caplog.text


def test_a_consumed_break_glass_token_is_logged_masked(
    change_window_service: ProtectedChangeWindowService, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    command = "systemctl restart nginx --key abc123xyz"
    token_data = change_window_service.issue_break_glass_token(
        host_alias="prod-server-01", command=command, reason="Emergency", ttl_seconds=300
    )
    is_valid, _ = change_window_service.verify_and_consume_token(
        token=token_data.token, host_alias="prod-server-01", command=command
    )
    assert is_valid
    assert "BREAK_GLASS_CONSUMED" in caplog.text
    assert "abc123xyz" not in caplog.text


def test_break_glass_service_keeps_no_copy_of_the_command(change_window_service: ProtectedChangeWindowService) -> None:
    command = "systemctl restart nginx --key Zx81qpLm"
    altered = "systemctl restart nginx --key Other999"
    token_data = change_window_service.issue_break_glass_token(
        host_alias="prod-server-01", command=command, reason="Emergency", ttl_seconds=300
    )
    rejected, _ = change_window_service.verify_and_consume_token(
        token=token_data.token, host_alias="prod-server-01", command=altered
    )
    unknown, _ = change_window_service.verify_and_consume_token(token="bg_unknown", host_alias="prod-server-01", command=altered)
    consumed, _ = change_window_service.verify_and_consume_token(
        token=token_data.token, host_alias="prod-server-01", command=command
    )
    assert (rejected, unknown, consumed) == (False, False, True)
    held = repr(vars(change_window_service)) + repr(token_data)
    assert "Zx81qpLm" not in held
    assert "Other999" not in held


def test_an_issued_break_glass_token_is_not_logged(
    change_window_service: ProtectedChangeWindowService, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING)
    token_data = change_window_service.issue_break_glass_token(
        host_alias="prod-server-01", command="systemctl restart nginx", reason="Emergency", ttl_seconds=300
    )
    assert "BREAK_GLASS_ISSUED" in caplog.text
    assert token_data.token not in caplog.text
