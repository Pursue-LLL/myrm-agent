"""``file_write_disabled`` — does a security policy unconditionally deny file writes."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.engine import file_write_disabled
from myrm_agent_harness.core.security.types import PermissionAction, PermissionRule, SecurityConfig


def _with_rule(config: SecurityConfig, rule: PermissionRule) -> SecurityConfig:
    return replace(config, ruleset=(*config.ruleset, rule))


class TestFileWriteDisabled:
    def test_no_policy_denies_nothing(self) -> None:
        assert file_write_disabled(None) is False

    def test_object_that_is_not_a_security_config_denies_nothing(self) -> None:
        assert file_write_disabled(MagicMock()) is False

    def test_web_chat_default_may_write(self) -> None:
        assert file_write_disabled(build_channel_security_config("web_chat", None)) is False

    def test_read_only_profile_denies_writes(self) -> None:
        assert file_write_disabled(SecurityConfig.readonly()) is True

    def test_cron_job_whose_declared_capabilities_exclude_file_write(self) -> None:
        config = build_channel_security_config("cron", None, declared_capabilities=("web_search",))
        assert file_write_disabled(config) is True

    def test_cron_job_that_declares_file_write_may_write(self) -> None:
        config = build_channel_security_config("cron", None, declared_capabilities=("file_write",))
        assert file_write_disabled(config) is False

    def test_a_catch_all_deny_rule_disables_writes(self) -> None:
        config = _with_rule(
            build_channel_security_config("web_chat", None), PermissionRule("file_write", "*", PermissionAction.DENY)
        )
        assert file_write_disabled(config) is True

    def test_a_deny_rule_for_one_path_does_not_disable_writes(self) -> None:
        config = _with_rule(
            build_channel_security_config("web_chat", None),
            PermissionRule("file_write", "/etc/*", PermissionAction.DENY),
        )
        assert file_write_disabled(config) is False

    def test_an_ask_rule_is_not_a_denial(self) -> None:
        config = _with_rule(
            build_channel_security_config("web_chat", None), PermissionRule("file_write", "*", PermissionAction.ASK)
        )
        assert file_write_disabled(config) is False
