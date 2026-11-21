"""A rule that names a path governs the file however the call spells it.

The rules ``private/*`` or ``/home/me/ws/private/*`` name a place, but a call can type the same file as
``./private/plan.md``, ``/workspace/private/plan.md``, a host path, ``docs/../private/plan.md`` or through a link, and
a rule matches the text it is given. The engine therefore reads each file a file tool opens in three forms (the typed
text, where the file lies, where it lies below the workspace) and the strictest verdict of the rules that name a
path decides. Blanket ``*`` rules judge the typed text only, so a run that denies everything and allows a list of
places keeps allowing that list, whichever way a link in its workspace path leads.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.security import engine
from myrm_agent_harness.agent.security.engine import evaluate_tool_call, merge
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="links are POSIX behaviour")

DENY = PermissionAction.DENY
ASK = PermissionAction.ASK
ALLOW = PermissionAction.ALLOW

# Every way a call can type the file ``private/plan.md`` of the workspace; ``<ws>`` stands for its host path.
SPELLINGS_OF_THE_PRIVATE_PLAN = [
    "private/plan.md",
    "./private/plan.md",
    "private//plan.md",
    "docs/../private/plan.md",
    "/workspace/private/plan.md",
    "<ws>/private/plan.md",
]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "private").mkdir(parents=True)
    (root / "docs").mkdir()
    return root


def _config(*rules: PermissionRule) -> SecurityConfig:
    return SecurityConfig(ruleset=merge(DEFAULT_RULESET, rules))


def _read(config: SecurityConfig, workspace: Path, typed: str) -> PermissionAction:
    return evaluate_tool_call(
        "file_read",
        {"paths": [typed.replace("<ws>", str(workspace))]},
        config,
        workspace_root=str(workspace),
        tool_name="file_read_tool",
    )[0]


def _write(config: SecurityConfig, workspace: Path, typed: str) -> PermissionAction:
    return evaluate_tool_call(
        "file_write",
        {"path": typed.replace("<ws>", str(workspace))},
        config,
        workspace_root=str(workspace),
        tool_name="file_write_tool",
    )[0]


@pytest.mark.parametrize("typed", SPELLINGS_OF_THE_PRIVATE_PLAN)
class TestARuleThatNamesAPlaceWithinTheWorkspace:
    def test_a_read_is_denied_in_every_spelling(self, workspace: Path, typed: str) -> None:
        assert _read(_config(PermissionRule("file_read", "private/*", DENY)), workspace, typed) == DENY

    def test_a_write_is_denied_in_every_spelling(self, workspace: Path, typed: str) -> None:
        assert _write(_config(PermissionRule("file_write", "private/*", DENY)), workspace, typed) == DENY

    def test_a_rule_that_asks_asks_in_every_spelling(self, workspace: Path, typed: str) -> None:
        assert _read(_config(PermissionRule("file_read", "private/*", ASK)), workspace, typed) == ASK


@pytest.mark.parametrize("typed", ["private/plan.md", "./private/plan.md", "/workspace/private/plan.md"])
def test_a_rule_that_names_the_host_path_governs_a_workspace_spelling(workspace: Path, typed: str) -> None:
    config = _config(PermissionRule("file_read", f"{workspace.resolve()}/private/*", DENY))

    assert _read(config, workspace, typed) == DENY


@POSIX_ONLY
def test_a_link_to_a_denied_place_is_denied(workspace: Path) -> None:
    (workspace / "shortcut").symlink_to("private", target_is_directory=True)
    config = _config(PermissionRule("file_read", "private/*", DENY))

    assert _read(config, workspace, "shortcut/plan.md") == DENY


def test_a_file_outside_the_denied_place_is_still_allowed(workspace: Path) -> None:
    config = _config(PermissionRule("file_read", "private/*", DENY))

    assert _read(config, workspace, "./docs/plan.md") == ALLOW
    assert _read(config, workspace, "/workspace/docs/plan.md") == ALLOW


def test_a_rule_of_another_permission_does_not_govern_a_read(workspace: Path) -> None:
    config = _config(PermissionRule("file_write", "private/*", DENY))

    assert _read(config, workspace, "./private/plan.md") == ALLOW


class TestBlanketRulesJudgeTheTypedTextOnly:
    """A run that denies everything and allows a list of places keeps allowing that list."""

    @POSIX_ONLY
    def test_an_allowed_place_reached_through_a_link_in_the_workspace_path_stays_allowed(self, tmp_path: Path) -> None:
        (tmp_path / "real" / "ws" / "docs").mkdir(parents=True)
        (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
        workspace = tmp_path / "link" / "ws"
        config = SecurityConfig(
            ruleset=(
                PermissionRule("file_read", "*", DENY),
                PermissionRule("file_read", f"{workspace}/docs/*", ALLOW),
            )
        )

        assert _read(config, workspace, "<ws>/docs/a.md") == ALLOW

    def test_a_run_that_denies_everything_but_a_list_keeps_its_verdicts(self, workspace: Path) -> None:
        config = SecurityConfig(
            ruleset=(
                PermissionRule("file_read", "*", DENY),
                PermissionRule("file_read", "docs/*", ALLOW),
            )
        )

        assert _read(config, workspace, "docs/a.md") == ALLOW
        assert _read(config, workspace, "private/a.md") == DENY

    def test_a_blanket_ask_does_not_turn_a_listed_place_into_an_ask(self, workspace: Path) -> None:
        config = SecurityConfig(
            ruleset=(
                PermissionRule("file_read", "*", ASK),
                PermissionRule("file_read", "docs/*", ALLOW),
            )
        )

        assert _read(config, workspace, "docs/a.md") == ALLOW


@pytest.mark.parametrize("folds_case", [True, False], ids=["case-insensitive-volume", "case-sensitive-volume"])
class TestOnAVolumeThatIgnoresCase:
    """``Private/plan.md`` is the file ``private/plan.md`` there, so a rule that refuses or asks covers it too."""

    @pytest.fixture(autouse=True)
    def _volume(self, monkeypatch: pytest.MonkeyPatch, folds_case: bool) -> None:
        monkeypatch.setattr(engine, "FOLDS_CASE", folds_case)

    @pytest.mark.parametrize("typed", ["Private/plan.md", "PRIVATE/PLAN.MD", "./Private/plan.md"])
    def test_a_rule_that_denies_covers_every_casing(self, workspace: Path, folds_case: bool, typed: str) -> None:
        config = _config(PermissionRule("file_read", "private/*", DENY))

        assert _read(config, workspace, typed) == (DENY if folds_case else ALLOW)

    def test_a_rule_that_asks_covers_every_casing(self, workspace: Path, folds_case: bool) -> None:
        config = _config(PermissionRule("file_write", "private/*", ASK))

        assert _write(config, workspace, "Private/plan.md") == (ASK if folds_case else ALLOW)

    def test_a_rule_that_allows_stays_exact(self, workspace: Path, folds_case: bool) -> None:
        config = SecurityConfig(
            ruleset=(
                PermissionRule("file_read", "*", ASK),
                PermissionRule("file_read", "docs/*", ALLOW),
            )
        )

        assert _read(config, workspace, "docs/a.md") == ALLOW
        assert _read(config, workspace, "Docs/a.md") == ASK

    def test_a_rule_on_a_command_is_matched_exactly(self, workspace: Path, folds_case: bool) -> None:
        config = SecurityConfig(
            ruleset=(
                PermissionRule("shell_exec", "*", ALLOW),
                PermissionRule("shell_exec", "deploy *", DENY),
            )
        )
        action, _ = evaluate_tool_call(
            "shell_exec",
            {"command": "DEPLOY now"},
            config,
            workspace_root=str(workspace),
            tool_name="bash_code_execute_tool",
        )

        assert action != DENY
