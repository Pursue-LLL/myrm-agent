"""Tests for skill-scoped OAuth credential injection in bash execution."""

from __future__ import annotations

from unittest.mock import MagicMock

from myrm_agent_harness.agent.meta_tools.bash._executor.executor import BashExecutor
from myrm_agent_harness.agent.security.types import EphemeralUserCredential, user_credentials_ctx
from myrm_agent_harness.toolkits.code_execution import ExecutionConfig, ExecutionContext
from myrm_agent_harness.toolkits.code_execution.executors.local._command_env import (
    build_command_env,
    collect_command_credentials,
    skill_secret_env,
)
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


def test_execution_context_carries_the_skill_settings_apart_from_the_global_env() -> None:
    mock_executor = MagicMock()
    mock_executor.config = ExecutionConfig()
    bash_executor = BashExecutor(executor=mock_executor)
    bash_executor.set_global_env({"GLOBAL_API_KEY": "global-secret"})

    def build(skill_env: dict[str, str] | None) -> ExecutionContext:
        return bash_executor._build_execution_context(
            prepared_code="echo hi",
            original_code="echo hi",
            mcp_config_items=None,
            session_id="s1",
            workspace=None,
            env_paths=None,
            working_dir=None,
            skill_names=["imap-smtp-email"] if skill_env else None,
            skill_env=skill_env,
        )

    with_skill = build({"EMAIL_IMAP_PASSWORD": "pw"})
    assert with_skill.skill_env == {"EMAIL_IMAP_PASSWORD": "pw"}
    assert with_skill.env is not None and with_skill.env["GLOBAL_API_KEY"] == "global-secret"
    assert build(None).skill_env is None


def test_skill_secret_env_keeps_only_the_secret_named_settings() -> None:
    settings = {"EMAIL_IMAP_HOST": "imap.example.test", "EMAIL_IMAP_PASSWORD": "pw", "LINEAR_API_KEY": "key"}

    assert skill_secret_env(settings) == {"EMAIL_IMAP_PASSWORD": "pw", "LINEAR_API_KEY": "key"}
    assert skill_secret_env(None) == {}
    assert skill_secret_env({}) == {}


def test_skill_secret_env_refuses_the_names_that_run_foreign_code() -> None:
    assert skill_secret_env({"LD_PRELOAD": "/tmp/x.so", "NODE_OPTIONS": "--require x", "LD_DEBUG": "all"}) == {}


def test_command_env_hands_skill_secrets_to_the_command_only() -> None:
    command_env = build_command_env(
        {"EMAIL_IMAP_HOST": "h", "EMAIL_IMAP_PASSWORD": "pw"},
        [],
        None,
        {"EMAIL_IMAP_HOST": "h", "EMAIL_IMAP_PASSWORD": "pw"},
    )

    assert command_env.sticky == {"EMAIL_IMAP_HOST": "h"}
    assert command_env.scoped == {"EMAIL_IMAP_PASSWORD": "pw"}


def test_command_env_without_a_skill_hands_over_no_secret() -> None:
    command_env = build_command_env({"EMAIL_IMAP_PASSWORD": "pw"}, None, None)

    assert command_env.sticky == {}
    assert command_env.scoped == {}


def test_credential_of_the_command_wins_over_a_skill_setting_of_the_same_name() -> None:
    token = user_credentials_ctx.set((EphemeralUserCredential(issuer="github", token="gh-token"),))
    try:
        command_env = build_command_env(None, None, None, {"GITHUB_TOKEN": "from-settings"})
    finally:
        user_credentials_ctx.reset(token)

    assert command_env.scoped == {"GITHUB_TOKEN": "gh-token"}


def test_shell_start_env_carries_no_credentials() -> None:
    token = user_credentials_ctx.set((EphemeralUserCredential(issuer="github", token="gh-token"),))
    try:
        env = LocalExecutor(config=ExecutionConfig())._build_bash_env(None)
        assert "GITHUB_TOKEN" not in env
    finally:
        user_credentials_ctx.reset(token)
