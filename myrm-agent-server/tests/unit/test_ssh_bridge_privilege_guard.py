"""Unit tests for SSHBridgeExecutor integration with Triad Delegation Privilege Guard.

[POS]
Validates that low-privilege initial requesters cannot leverage SSHBridgeExecutor
to run unauthorized commands, and verifies that approved/privileged requesters pass.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.agent.middlewares._session_context import (
    set_delegation_token,
)
from myrm_agent_harness.agent.security.delegation.models import (
    SubjectIdentity,
    SubjectType,
    TriadDelegationToken,
)

from app.services.ssh_bridge.executor import SSHBridgeExecutor
from app.services.ssh_bridge.manager import SSHAssetManager
from app.services.ssh_bridge.models import SSHAuthMethod, SSHHostAsset


@pytest.fixture
def test_setup() -> tuple[SSHBridgeExecutor, str]:
    """Setup an in-memory SSH asset manager with a mock runner."""
    manager = SSHAssetManager()
    asset = SSHHostAsset(
        asset_id="asset-prod-01",
        alias="prod-server",
        host_name="192.168.1.10",
        port=22,
        user="deployer",
        auth_method=SSHAuthMethod.PASSWORD,
        is_read_only=False,
    )
    manager.register_asset(asset)

    def mock_runner(a: SSHHostAsset, cmd: str, timeout: float) -> tuple[int, str, str]:
        return 0, f"Executed: {cmd}", ""

    executor = SSHBridgeExecutor(asset_manager=manager, custom_remote_runner=mock_runner)
    return executor, "prod-server"


def test_ssh_bridge_blocked_when_requester_lacks_write_privilege(
    test_setup: tuple[SSHBridgeExecutor, str],
) -> None:
    """Verify that a requester with only read-only scope is blocked from executing write commands."""
    executor, alias = test_setup

    # Alice only has ssh:exec:read scope
    requester = SubjectIdentity(
        subject_id="user_alice_reader",
        subject_type=SubjectType.HUMAN,
        display_name="Alice Reader",
        scopes=frozenset({"ssh:exec:read"}),
    )
    agent = SubjectIdentity(
        subject_id="agent_devops",
        subject_type=SubjectType.AGENT,
        display_name="DevOps Agent",
        scopes=frozenset({"ssh:exec:read", "ssh:exec:write"}),
    )
    token = TriadDelegationToken(initial_requester=requester, executor_agent=agent)
    set_delegation_token(token)

    try:
        # Attempt to run a write command on prod-server
        result = executor.execute_command(alias, "echo 'malicious_config' > /etc/app.conf")
        assert result.is_blocked is True
        assert result.exit_code == 126
        assert result.block_reason == "PRIVILEGE_AMPLIFICATION_BLOCKED"
        assert "Privilege Amplification Gate Blocked" in result.stderr

        # Safe read command passes
        read_result = executor.execute_command(alias, "ls -la /var/log")
        assert read_result.is_blocked is False
        assert read_result.exit_code == 0
        assert "Executed: ls -la /var/log" in read_result.stdout
    finally:
        set_delegation_token(None)


def test_ssh_bridge_allowed_when_requester_has_write_privilege(
    test_setup: tuple[SSHBridgeExecutor, str],
) -> None:
    """Verify that a requester with write scope is permitted to execute commands."""
    executor, alias = test_setup

    # Bob has full write privilege
    requester = SubjectIdentity(
        subject_id="user_bob_admin",
        subject_type=SubjectType.HUMAN,
        display_name="Bob Admin",
        scopes=frozenset({"ssh:exec:write", "ssh:exec:read"}),
    )
    agent = SubjectIdentity(
        subject_id="agent_devops",
        subject_type=SubjectType.AGENT,
        display_name="DevOps Agent",
        scopes=frozenset({"ssh:exec:read", "ssh:exec:write"}),
    )
    token = TriadDelegationToken(initial_requester=requester, executor_agent=agent)
    set_delegation_token(token)

    try:
        result = executor.execute_command(alias, "systemctl restart my-service")
        assert result.is_blocked is False
        assert result.exit_code == 0
        assert "Executed: systemctl restart my-service" in result.stdout
    finally:
        set_delegation_token(None)
