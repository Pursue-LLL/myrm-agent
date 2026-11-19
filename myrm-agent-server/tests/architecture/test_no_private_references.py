"""Architecture tests on tracked text files.

They must not point into the private dev shell, and must not tell readers to run developer commands through the user CLI.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_USER_CLI = _REPO_ROOT / "scripts" / "myrm"
# Names that resolve only inside the private dev shell: its planning directory (with or without a
# trailing slash), its own name, its maintainer quick-start document, the directory a maintainer keeps
# sibling projects in on their own machine, and planning item ids, matched case-insensitively. The id
# alternative uses explicit non-word boundaries instead of \b so an id glued to CJK text is still
# caught, while chat topic keys (leading underscore) and longer digit runs are not. The patterns and
# the samples are assembled from fragments so this file does not match itself.
_DIR = "temp-" + "docs"
_SHELL = "vortex" + "ai"
_QUICKSTART = "MAINTAINER_" + "QUICKSTART"
_CHECKOUT = "~/projects/" + "AI/"
_ID = "topic" + "_12"
_PRIVATE_REFERENCE_PATTERN = rf"{_DIR}|{_SHELL}|{_QUICKSTART}|{_CHECKOUT}|(^|[^A-Za-z0-9_])topic_[0-9]{{2}}([^0-9]|$)"

# Subcommands of the developer CLI (./myrm-dev, private dev shell). The user CLI dispatches none of
# them, so a reader told to run one through it only gets the help text. A command inside quotes is
# test data (the cron lifecycle guard tests feed such strings to the guard) and is not matched.
_CLI = "./" + "myrm"
_DEV_ONLY_COMMANDS = ("ready", "test", "restart", "isolate", "verify-api", "harness")
_DEV_COMMAND_PATTERN = rf"{re.escape(_CLI)} ({'|'.join(_DEV_ONLY_COMMANDS)})([ `]|$)"
_MAX_REPORTED_HITS = 20

_PATTERN_CASES = [
    pytest.param(f"see {_DIR}/roadmap/a.md for details", True, id="path"),
    pytest.param(f"{_ID} is planned", True, id="id-at-line-start"),
    pytest.param(f"ends with {_ID}", True, id="id-at-line-end"),
    pytest.param(f"planned in ({_ID})", True, id="id-in-parentheses"),
    pytest.param(f"条目{_ID}已完成", True, id="id-glued-to-cjk"),
    pytest.param(f"prose names {_DIR} only", True, id="directory-name"),
    pytest.param(f"prose names {_DIR.title()} only", True, id="directory-name-other-case"),
    pytest.param(f"the {_SHELL} root", True, id="dev-shell-name"),
    pytest.param(f"the {_SHELL.upper()} root", True, id="dev-shell-name-other-case"),
    pytest.param(f"see {_QUICKSTART}.md", True, id="quick-start-document"),
    pytest.param(f"built from {_CHECKOUT}chrome-agent", True, id="local-checkout-path"),
    pytest.param("placeholder ~/projects/some-sdk", False, id="generic-home-path"),
    pytest.param(f"chat key _{_ID}", False, id="chat-topic-key"),
    pytest.param(f"my{_ID}", False, id="id-inside-a-word"),
    pytest.param(f"{_ID}3", False, id="three-digit-number"),
]

_DEV_COMMAND_CASES = [
    pytest.param(f"run {_CLI} ready --chrome first", True, id="command-with-flags"),
    pytest.param(f"`{_CLI} test`", True, id="command-in-backticks"),
    pytest.param(f"then {_CLI} restart", True, id="command-at-line-end"),
    pytest.param(f"run {_CLI}-dev ready", False, id="developer-cli"),
    pytest.param(f"run {_CLI} start", False, id="user-command"),
    pytest.param(f'guard input "{_CLI} restart"', False, id="quoted-test-data"),
]


def _git_grep(pattern: str, args: list[str], cwd: Path, *, ignore_case: bool) -> list[str]:
    """Return ``path:line:text`` rows matching ``pattern`` (git grep status 1 means none)."""
    result = subprocess.run(
        ["git", "grep", "-I", "-n", *(["-i"] if ignore_case else []), "-E", "-e", pattern, *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed with status {result.returncode}: {result.stderr.strip()}")
    return result.stdout.splitlines()


def _fail_on_hits(hits: list[str], reason: str) -> None:
    if not hits:
        return
    detail = "\n".join(row[:200] for row in hits[:_MAX_REPORTED_HITS])
    if len(hits) > _MAX_REPORTED_HITS:
        detail += f"\n... and {len(hits) - _MAX_REPORTED_HITS} more"
    pytest.fail(f"{reason}\n{detail}")


def _matches_sample(pattern: str, line: str, tmp_path: Path, *, ignore_case: bool) -> bool:
    sample = tmp_path / "sample.txt"
    sample.write_text(line + "\n", encoding="utf-8")
    return bool(_git_grep(pattern, ["--no-index", "--", sample.name], cwd=tmp_path, ignore_case=ignore_case))


@pytest.mark.parametrize(("line", "expected"), _PATTERN_CASES)
def test_pattern_matches_exactly_the_private_reference_shapes(line: str, expected: bool, tmp_path: Path) -> None:
    assert _matches_sample(_PRIVATE_REFERENCE_PATTERN, line, tmp_path, ignore_case=True) is expected


@pytest.mark.parametrize(("line", "expected"), _DEV_COMMAND_CASES)
def test_pattern_matches_exactly_the_developer_command_shapes(line: str, expected: bool, tmp_path: Path) -> None:
    assert _matches_sample(_DEV_COMMAND_PATTERN, line, tmp_path, ignore_case=False) is expected


def test_developer_commands_are_not_user_cli_commands() -> None:
    labels = {
        name
        for group in re.findall(r"^    ([^\s()]+)\)", _USER_CLI.read_text(encoding="utf-8"), re.MULTILINE)
        for name in group.split("|")
    }
    assert {"setup", "start", "stop"} <= labels, "user CLI dispatch table not found"
    assert labels.isdisjoint(_DEV_ONLY_COMMANDS), "the user CLI now dispatches a command this guard treats as developer-only"


def test_tracked_text_files_have_no_private_references() -> None:
    _fail_on_hits(
        _git_grep(_PRIVATE_REFERENCE_PATTERN, ["--", "."], cwd=_REPO_ROOT, ignore_case=True),
        "Tracked files reference the private dev shell (its planning directory, name, quick-start document, "
        "a maintainer's local checkout path or item ids; none of them resolve in this repo). "
        "Use in-repo _ARCH.md or brand docs instead.",
    )


def test_tracked_text_files_do_not_run_developer_commands_through_the_user_cli() -> None:
    _fail_on_hits(
        _git_grep(_DEV_COMMAND_PATTERN, ["--", "."], cwd=_REPO_ROOT, ignore_case=False),
        "Tracked files tell the reader to run a developer command through the user CLI, which does not "
        "dispatch it. Developer commands run through ./myrm-dev.",
    )
