"""Explicit rules outrank the baseline ruleset.

The agent ceiling judges only the rules an agent itself added, and the local-mode browser relaxation is a layer
of the baseline, so a saved or agent rule that names the same permission always outranks it.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.config import parse_security_config
from myrm_agent_harness.agent.security.engine import evaluate
from myrm_agent_harness.agent.security.types import PermissionAction, PermissionRule

ALLOW, ASK, DENY = PermissionAction.ALLOW, PermissionAction.ASK, PermissionAction.DENY

# An agent config that carries no permission rules of its own.
_AGENT_WITHOUT_RULES: dict[str, object] = {"networkAllowlist": ["example.com"]}


def _verdict(
    permission: str,
    target: str = "*",
    *,
    user: dict[str, object] | None = None,
    agent: dict[str, object] | None = None,
    local: bool = False,
) -> PermissionAction:
    config = build_channel_security_config("web_chat", user, agent_security_raw=agent, local_mode=local)
    return evaluate(permission, target, config.ruleset).action


class TestAgentCeilingJudgesOnlyTheAgentsOwnRules:
    def test_an_agent_config_without_rules_keeps_every_saved_denial(self) -> None:
        user: dict[str, object] = {"permissions": {"file_edit": "deny", "shell_exec": "deny"}}
        assert _verdict("file_edit", user=user, agent=_AGENT_WITHOUT_RULES) is DENY
        assert _verdict("shell_exec", user=user, agent=_AGENT_WITHOUT_RULES) is DENY

    def test_an_agent_config_without_rules_keeps_a_saved_allow(self) -> None:
        user: dict[str, object] = {"permissions": {"shell_exec": "allow"}}
        assert _verdict("shell_exec", user=user, agent=_AGENT_WITHOUT_RULES) is ALLOW

    def test_an_agent_rule_that_relaxes_a_saved_denial_is_rejected(self) -> None:
        user: dict[str, object] = {"permissions": {"file_edit": "deny"}}
        assert _verdict("file_edit", user=user, agent={"permissions": {"file_edit": "allow"}}) is DENY

    def test_an_agent_rule_may_tighten_a_saved_allow(self) -> None:
        user: dict[str, object] = {"permissions": {"shell_exec": "allow"}}
        assert _verdict("shell_exec", user=user, agent={"permissions": {"shell_exec": "ask"}}) is ASK

    def test_an_allow_list_agent_keeps_its_named_allows(self) -> None:
        user: dict[str, object] = {"permissions": {"file_edit": "deny"}}
        agent: dict[str, object] = {"permissions": {"*": "deny", "file_read": "allow"}}
        assert _verdict("web_search", user=user, agent=agent) is DENY
        assert _verdict("file_read", user=user, agent=agent) is ALLOW
        assert _verdict("file_edit", user=user, agent=agent) is DENY


class TestLocalBrowserRelaxationIsBaseline:
    def test_local_mode_relaxes_the_browser_by_default(self) -> None:
        assert _verdict("browser_fill") is ASK
        assert _verdict("browser_fill", local=True) is ALLOW
        assert _verdict("browser_navigate", "localhost:3000") is DENY
        assert _verdict("browser_navigate", "localhost:3000", local=True) is ALLOW

    def test_a_saved_rule_outranks_the_relaxation(self) -> None:
        user: dict[str, object] = {"permissions": {"browser_fill": "ask", "browser_upload": "deny"}}
        assert _verdict("browser_fill", user=user, local=True) is ASK
        assert _verdict("browser_upload", user=user, local=True) is DENY
        assert _verdict("browser_download", user=user, local=True) is ALLOW

    def test_a_saved_wildcard_outranks_the_relaxation(self) -> None:
        user: dict[str, object] = {"permissions": {"*": "ask"}}
        assert _verdict("browser_fill", user=user, local=True) is ASK

    def test_an_agent_denial_outranks_the_relaxation(self) -> None:
        agent: dict[str, object] = {"permissions": {"browser_download": "deny"}}
        user: dict[str, object] = {"permissions": {"file_edit": "deny"}}
        assert _verdict("browser_download", agent=agent, local=True) is DENY
        assert _verdict("browser_download", user=user, agent=agent, local=True) is DENY

    def test_the_relaxation_stays_for_what_the_saved_rules_do_not_name(self) -> None:
        user: dict[str, object] = {"permissions": {"file_edit": "deny"}}
        assert _verdict("browser_fill", user=user, local=True) is ALLOW
        assert _verdict("browser_navigate", "localhost:3000", user=user, local=True) is ALLOW


class TestParseOverABaseRuleset:
    _BASE = (PermissionRule("browser_fill", "*", ALLOW),)

    def test_explicit_rules_are_laid_behind_the_base(self) -> None:
        config = parse_security_config({"permissions": {"browser_fill": "ask"}}, base_ruleset=self._BASE)
        assert config is not None
        assert config.ruleset == (*self._BASE, PermissionRule("browser_fill", "*", ASK))

    def test_a_config_without_rules_is_the_base(self) -> None:
        config = parse_security_config({"approvalTimeoutSeconds": 60}, base_ruleset=self._BASE)
        assert config is not None
        assert config.ruleset == self._BASE
