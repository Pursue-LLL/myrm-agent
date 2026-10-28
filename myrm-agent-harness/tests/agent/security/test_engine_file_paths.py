"""The permission engine judges every file a file tool names, whatever the argument is called.

``file_read_tool`` receives its files in ``paths`` (a list) or under one of a dozen aliases. The path-zone
verdict and the rule targets used to read ``path`` alone, so a read through any other spelling was never
refused, never asked about and never matched against the ``*.env`` and ``*.pem`` rules.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.agent.security.engine import check_tool_path_policy, evaluate_tool_call, merge
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PathPolicy,
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)
from myrm_agent_harness.core.security.tool_registry.file_args import FILE_ARG_KEYS

_WORKSPACE = "/Users/me/ws"
_CONFIG = SecurityConfig(path_policy=PathPolicy(forbidden_paths=frozenset({"/Users/me/.ssh"}), access_roots=()))


def _verdict(
    args: dict[str, object], config: SecurityConfig = _CONFIG, permission: str = "file_read"
) -> PermissionAction:
    tool_name = "file_read_tool" if permission == "file_read" else "file_write_tool"
    return evaluate_tool_call(permission, args, config, workspace_root=_WORKSPACE, tool_name=tool_name)[0]


@pytest.mark.parametrize("key", FILE_ARG_KEYS)
class TestEverySpellingIsJudged:
    def test_forbidden_zone_is_denied(self, key: str) -> None:
        assert _verdict({key: ["/Users/me/.ssh/id_rsa"]}) == PermissionAction.DENY
        assert _verdict({key: "/Users/me/.ssh/id_rsa"}) == PermissionAction.DENY

    def test_outside_the_allowed_zones_asks(self, key: str) -> None:
        assert _verdict({key: ["/Users/me/Downloads/bill.csv"]}) == PermissionAction.ASK

    def test_inside_the_workspace_is_allowed(self, key: str) -> None:
        assert _verdict({key: ["src/a.py", "/Users/me/ws/b.py"]}) == PermissionAction.ALLOW

    def test_relative_escape_asks(self, key: str) -> None:
        assert _verdict({key: ["../skills/off/SKILL.md"]}) == PermissionAction.ASK

    def test_secret_file_rule_applies(self, key: str) -> None:
        assert _verdict({key: ["config/.env"]}) == PermissionAction.ASK


class TestStrictestVerdictWins:
    def test_one_bad_file_among_good_ones_decides(self) -> None:
        assert _verdict({"paths": ["src/a.py", "/Users/me/Downloads/b.csv", "src/c.py"]}) == PermissionAction.ASK

    def test_deny_is_not_weakened_by_an_earlier_ask_or_allow(self) -> None:
        assert _verdict({"paths": ["src/a.py", "/elsewhere/b.csv", "/Users/me/.ssh/id_rsa"]}) == PermissionAction.DENY

    def test_rule_target_of_a_later_file_decides(self) -> None:
        assert _verdict({"paths": ["a.py", "config/.env", "b.py"]}) == PermissionAction.ASK

    def test_explicit_deny_rule_on_a_later_file_is_not_weakened(self) -> None:
        config = SecurityConfig(
            ruleset=merge(DEFAULT_RULESET, (PermissionRule("file_read", "*.pem", PermissionAction.DENY),))
        )
        assert _verdict({"paths": ["config/.env", "certs/a.pem"]}, config) == PermissionAction.DENY

    def test_range_suffix_does_not_hide_a_secret_file(self) -> None:
        assert _verdict({"paths": [".env:1-5"]}) == PermissionAction.ASK


class TestVirtualNamespacesAreNotJudgedAsHostFiles:
    @pytest.mark.parametrize("path", ["/mcp/gmail/send_email.md", "vault://0a1b2c:1-50", "https://example.com/a.txt"])
    def test_no_zone_verdict_and_no_prompt(self, path: str) -> None:
        assert check_tool_path_policy("file_read", {"paths": [path]}, _CONFIG, _WORKSPACE) is None
        assert _verdict({"paths": [path]}) == PermissionAction.ALLOW


class TestSameVerdictAsTheSingularArgument:
    @pytest.mark.parametrize(
        "path",
        ["/workspace/a.py", "~/notes.md", "src/a.py", "/Users/me/.ssh/config", "../x", "config/.env", "/etc/hosts"],
    )
    def test_paths_and_path_agree(self, path: str) -> None:
        assert _verdict({"paths": [path]}) == _verdict({"path": path})


class TestCheckToolPathPolicy:
    def test_names_no_file(self) -> None:
        assert check_tool_path_policy("file_read", {"pattern": "*.py"}, _CONFIG, _WORKSPACE) is None
        assert check_tool_path_policy("file_read", {"paths": []}, _CONFIG, _WORKSPACE) is None

    def test_returns_the_strictest_verdict_with_its_reason(self) -> None:
        verdict = check_tool_path_policy(
            "file_read", {"paths": ["src/a.py", "/Users/me/.ssh/id_rsa"]}, _CONFIG, _WORKSPACE
        )
        assert verdict is not None
        assert verdict[0] == PermissionAction.DENY
        assert "/Users/me/.ssh/id_rsa" in verdict[1]

    def test_write_permission_still_checks_path(self) -> None:
        assert _verdict({"path": "/Users/me/Downloads/a.txt"}, permission="file_write") == PermissionAction.ASK


@pytest.mark.parametrize("key", FILE_ARG_KEYS)
class TestJsonArrayStringIsJudgedLikeTheList:
    """Models often send an array argument as its JSON text; the tool reads it as the array, so the verdict must too."""

    @pytest.mark.parametrize(
        "files",
        [
            ["/Users/me/.ssh/id_rsa"],
            ["/Users/me/Downloads/bill.csv"],
            ["src/a.py", "/Users/me/ws/b.py"],
            ["src/a.py", "/Users/me/Downloads/b.csv"],
            ["config/.env"],
            ["../skills/off/SKILL.md"],
        ],
    )
    def test_same_verdict_as_the_list(self, key: str, files: list[str]) -> None:
        assert _verdict({key: json.dumps(files)}) == _verdict({key: files})

    def test_outside_file_inside_the_text_asks(self, key: str) -> None:
        assert _verdict({key: '["/Users/me/Downloads/bill.csv"]'}) == PermissionAction.ASK

    def test_forbidden_file_inside_the_text_is_denied(self, key: str) -> None:
        assert _verdict({key: '["src/a.py", "/Users/me/.ssh/id_rsa"]'}) == PermissionAction.DENY
