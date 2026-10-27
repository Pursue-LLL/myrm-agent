"""Tests for skill-scoped OAuth credential injection in bash execution."""

from __future__ import annotations

from unittest.mock import MagicMock

from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.agent.security.types import EphemeralUserCredential, user_credentials_ctx
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig
from myrm_agent_harness.toolkits.code_execution.executors.local._command_env import collect_command_credentials
from myrm_agent_harness.toolkits.code_execution.executors.local.executor import LocalExecutor


def test_bash_executor_scopes_issuers_when_skill_detected() -> None:
    mock_executor = MagicMock()
    mock_executor.config = ExecutionConfig()
    bash_executor = BashExecutor(executor=mock_executor)
    bash_executor.set_skill_oauth_issuers({"google-workspace": "google_workspace"})

    assert bash_executor._resolve_allowed_credential_issuers(None) is None
    assert bash_executor._resolve_allowed_credential_issuers([]) is None
    assert bash_executor._resolve_allowed_credential_issuers(["google-workspace"]) == ["google_workspace"]
    assert bash_executor._resolve_allowed_credential_issuers(["unknown-skill"]) == []


def test_command_credentials_are_scoped_by_allowed_issuers() -> None:
    cred_google = EphemeralUserCredential(issuer="google_workspace", token="gw-token")
    cred_github = EphemeralUserCredential(issuer="github", token="gh-token")
    token = user_credentials_ctx.set((cred_google, cred_github))

    try:
        all_env = collect_command_credentials(None, None)
        assert all_env["GOOGLE_WORKSPACE_TOKEN"] == "gw-token"
        assert all_env["GITHUB_TOKEN"] == "gh-token"

        scoped_env = collect_command_credentials(["google_workspace"], None)
        assert scoped_env["GOOGLE_WORKSPACE_TOKEN"] == "gw-token"
        assert "GITHUB_TOKEN" not in scoped_env

        assert collect_command_credentials([], None) == {}
    finally:
        user_credentials_ctx.reset(token)


def test_shell_start_env_carries_no_credentials() -> None:
    token = user_credentials_ctx.set((EphemeralUserCredential(issuer="github", token="gh-token"),))
    try:
        env = LocalExecutor(config=ExecutionConfig())._build_bash_env(None)
        assert "GITHUB_TOKEN" not in env
    finally:
        user_credentials_ctx.reset(token)
