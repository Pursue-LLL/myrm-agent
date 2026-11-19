"""The text a judge reads from a shell call is the text the tool runs, and no other.

The approval layers read the raw arguments the model sent, before the tool's input model validates them. The bash
tool runs ``command``; ``bash_process_tool`` types ``data`` into a running process. A key the model adds on top
(``command`` on a stdin call, ``code`` on a bash call) is dropped by the input model, so a judge that read it would
approve, deny or review text that never runs while the text that runs goes unjudged.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.meta_tools.bash._tool.helpers import BashInput
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import _BashProcessInput
from myrm_agent_harness.agent.security.checks import check_shell_threats
from myrm_agent_harness.agent.security.command_rules import (
    COMMAND_BEARING_PERMISSIONS,
    COMMAND_TEXT_KEY,
    command_text,
)
from myrm_agent_harness.agent.security.engine import _resolve_target, evaluate_tool_call, merge
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)
from myrm_agent_harness.core.security.tool_registry import resolve_permission_type

ALLOW, ASK, DENY = PermissionAction.ALLOW, PermissionAction.ASK, PermissionAction.DENY

STDIN, SHELL = "shell_exec", "code_interpreter"
STDIN_ACTIONS = ("write_stdin", "submit_stdin", "close_stdin", "kill")
# Argument names that look like a command but are no field of ``bash_process_tool``: text under them is never typed.
SHADOW_KEYS = ("command", "code")


def config_with(*rules: PermissionRule, command_denylist: tuple[str, ...] = ()) -> SecurityConfig:
    """The default rules plus *rules*; later rules win, as for a user profile."""
    return SecurityConfig(ruleset=merge(DEFAULT_RULESET, rules), command_denylist=command_denylist)


def verdict(permission: str, tool_input: dict[str, object], config: SecurityConfig) -> PermissionAction:
    return evaluate_tool_call(permission, tool_input, config)[0]


class TestTheMappingFollowsTheTools:
    """``COMMAND_TEXT_KEY`` is the one place that says which field each tool runs; the tools' models bind it."""

    def test_every_permission_a_shell_tool_resolves_to_names_a_command_field(self) -> None:
        resolved = {resolve_permission_type("bash_code_execute_tool", {})} | {
            resolve_permission_type("bash_process_tool", {"action": action}) for action in STDIN_ACTIONS
        }
        assert resolved == set(COMMAND_TEXT_KEY) == set(COMMAND_BEARING_PERMISSIONS)

    def test_the_named_field_is_a_field_of_the_tools_input_model(self) -> None:
        assert COMMAND_TEXT_KEY[SHELL] in BashInput.model_fields
        assert COMMAND_TEXT_KEY[STDIN] in _BashProcessInput.model_fields

    def test_the_input_models_drop_every_other_key_the_judges_used_to_read(self) -> None:
        bash = BashInput.model_validate({"reason": "List the build output", "command": "ls", "code": "x", "data": "y"})
        stdin = _BashProcessInput.model_validate({"action": "write_stdin", "pid": 7, "data": "ls", "command": "x"})

        assert bash.model_dump().keys().isdisjoint({"code", "data"})
        assert stdin.model_dump().keys().isdisjoint({"command", "code"})

    @pytest.mark.parametrize(
        ("permission", "tool_input", "expected"),
        [
            pytest.param(SHELL, {"command": "  ls -la \n"}, "ls -la", id="shell-trimmed"),
            pytest.param(SHELL, {"command": "ls", "code": "rm -rf /", "data": "y"}, "ls", id="shell-ignores-others"),
            pytest.param(SHELL, {"code": "rm -rf /"}, "", id="shell-without-command"),
            pytest.param(STDIN, {"data": "yes"}, "yes", id="stdin-data"),
            pytest.param(STDIN, {"data": "yes", "command": "rm -rf /", "code": "z"}, "yes", id="stdin-ignores-others"),
            pytest.param(STDIN, {"command": "rm -rf /"}, "", id="stdin-without-data"),
            pytest.param("file_read", {"command": "ls", "data": "y"}, "", id="no-command-field"),
            pytest.param(SHELL, {"command": None}, "", id="none-is-no-text"),
        ],
    )
    def test_command_text_reads_only_the_field_the_tool_runs(
        self, permission: str, tool_input: dict[str, object], expected: str
    ) -> None:
        assert command_text(permission, tool_input) == expected


class TestTheEngineJudgesWhatRuns:
    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_the_pattern_target_of_a_stdin_call_is_its_typed_text(self, shadow: str) -> None:
        assert _resolve_target(STDIN, {"data": "yes", shadow: "ls"}) == "yes"

    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_a_read_only_text_in_an_ignored_key_does_not_auto_allow_the_typed_text(self, shadow: str) -> None:
        assert verdict(STDIN, {"data": "rm -rf build", shadow: "ls"}, config_with()) == ASK

    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_an_allow_pattern_matching_an_ignored_key_does_not_allow_the_typed_text(self, shadow: str) -> None:
        config = config_with(PermissionRule(STDIN, "terraform *", ALLOW))

        assert verdict(STDIN, {"data": "terraform plan"}, config) == ALLOW
        assert verdict(STDIN, {"data": "rm -rf build", shadow: "terraform plan"}, config) == ASK

    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_a_deny_pattern_for_the_typed_text_holds_whatever_an_ignored_key_says(self, shadow: str) -> None:
        config = config_with(PermissionRule(STDIN, "rm *", DENY))

        assert verdict(STDIN, {"data": "rm -rf build", shadow: "ls"}, config) == DENY

    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_the_command_denylist_reads_the_typed_text(self, shadow: str) -> None:
        config = config_with(command_denylist=("rm -rf*",))

        assert verdict(STDIN, {"data": "rm -rf build", shadow: "ls"}, config) == DENY

    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_text_in_an_ignored_key_is_never_judged(self, shadow: str) -> None:
        config = config_with(PermissionRule(STDIN, "rm *", DENY), command_denylist=("rm -rf*",))

        assert verdict(STDIN, {"data": "ls", shadow: "rm -rf build"}, config) == ALLOW

    @pytest.mark.parametrize("shadow", ["code", "data"])
    def test_the_shell_tool_is_judged_on_its_command_alone(self, shadow: str) -> None:
        config = config_with(PermissionRule(SHELL, "rm *", DENY))

        assert verdict(SHELL, {"command": "rm -rf build", shadow: "ls"}, config) == DENY
        assert verdict(SHELL, {"command": "ls", shadow: "rm -rf build"}, config) == ALLOW


class TestTheThreatAnalyzerSeesWhatRuns:
    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_a_blocked_command_typed_into_a_process_is_blocked(self, shadow: str) -> None:
        assert check_shell_threats(STDIN, {"data": "rm -rf /", shadow: "ls"})[0] == DENY

    @pytest.mark.parametrize("shadow", SHADOW_KEYS)
    def test_a_blocked_text_in_an_ignored_key_is_not_a_threat(self, shadow: str) -> None:
        assert check_shell_threats(STDIN, {"data": "ls -la", shadow: "rm -rf /"}) == (None, "")

    def test_the_shell_tool_is_analysed_on_its_command(self) -> None:
        assert check_shell_threats(SHELL, {"command": "echo a\x00rm -rf /", "code": "ls"})[0] == DENY
        assert check_shell_threats(SHELL, {"command": "ls", "code": "echo a\x00rm -rf /"}) == (None, "")
