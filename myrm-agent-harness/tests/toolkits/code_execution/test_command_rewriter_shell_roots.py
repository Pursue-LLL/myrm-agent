"""A workspace root the shell would split or expand still reaches the shell as one path.

``/workspace`` becomes the real workspace root as text inside the command. A root holding a space, a comma, a
parenthesis, ``&``, ``;``, ``$`` or an apostrophe is quoted wherever a POSIX shell reads the match as plain text, so
every unquoted form below, run by a real bash, sees one word. Inside quotes, in a command with a heredoc and for a
non-POSIX shell the root goes in as typed.
"""

from __future__ import annotations

import itertools
import shlex
import shutil
import string
import subprocess
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.common.command_rewriter import CommandRewriter

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

_ROOT = "<root>"

# Folder names a user can pick: a shell given one as plain text splits, expands or cuts it short.
_SPECIAL_ROOT_NAMES = [
    "My Docs",
    "project (1)",
    "R&D",
    "John's Docs",
    "a;b",
    "dollar$HOME",
    "我的 项目",
    "Q3 Report - final",
]
# One folder name per ASCII punctuation mark (a path separator cannot be in a name; Windows rejects some marks).
_PUNCTUATION_ROOT_NAMES = [] if sys.platform == "win32" else [f"a{mark}b" for mark in string.punctuation if mark != "/"]
# Roots every POSIX shell reads as one literal word: they go in as typed.
_PLAIN_ROOTS = ["/data/agent/ws1", "/Users/me/我的项目", "/srv/a-b_c.d@e+f=g:h%j"]
_COMMANDS_NAMING_THE_ROOT = [
    "cd /workspace && ls",
    'cat "/workspace/a b.txt"',
    "tar -C/workspace -xf a.tar",
    "ls /workspace/*.txt",
    "PYTHONPATH=/workspace/a:/workspace/b tool",
]
# Where a shell reads /workspace as a word: the command, and what it prints with <root> for the real root.
_WORD_CONTEXTS = {
    "argument": ("printf '[%s]' /workspace/x.txt", "[<root>/x.txt]"),
    "glued option value": ("printf '[%s]' -r/workspace/x.txt", "[-r<root>/x.txt]"),
    "assignment": ('P=/workspace/x.txt; printf "[%s]" "$P"', "[<root>/x.txt]"),
    "input redirect": ("cat < /workspace/x.txt", "hello"),
    "cd": ("cd /workspace && cat x.txt", "hello"),
    "glob suffix": ("cat /workspace/*.txt", "hello"),
    "here-string": ("cat <<< /workspace/x.txt", "<root>/x.txt\n"),
    "command substitution": ("echo $(cat /workspace/x.txt)", "hello\n"),
    "brace list": ("printf '[%s]' {/workspace/x.txt,/workspace/y.txt}", "[<root>/x.txt][<root>/y.txt]"),
}
# A punctuation mark is read four ways: as an argument, glued to an option, as an assigned value, in a brace list.
_PUNCTUATION_CONTEXTS = ("argument", "glued option value", "assignment", "brace list")
_ROOT_CASES = [
    *itertools.product(_SPECIAL_ROOT_NAMES, _WORD_CONTEXTS),
    *itertools.product(_PUNCTUATION_ROOT_NAMES, _PUNCTUATION_CONTEXTS),
]


def _rewrite(command: str, root: Path | str, *, posix_shell: bool = True) -> str:
    return CommandRewriter().rewrite_workspace_paths(command, Path(root), posix_shell=posix_shell)


def _make_root(tmp_path: Path, name: str) -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / "x.txt").write_text("hello", encoding="utf-8")
    return root


def _shell_output(command: str, root: Path) -> str:
    done = subprocess.run(["bash", "-c", _rewrite(command, root)], capture_output=True, text=True, check=False)
    return done.stdout


class TestRootsTheShellWouldSplit:
    @pytest.mark.parametrize(("name", "context"), _ROOT_CASES)
    def test_a_root_read_as_plain_text_stays_one_path(self, tmp_path: Path, name: str, context: str) -> None:
        root = _make_root(tmp_path, name)
        command, expected = _WORD_CONTEXTS[context]

        assert _shell_output(command, root) == expected.replace(_ROOT, str(root))

    @pytest.mark.parametrize("name", ["x; touch MARK; y", "ws $(touch MARK)", "ws `touch MARK`"])
    def test_a_folder_name_is_never_run_as_a_command(self, tmp_path: Path, name: str) -> None:
        marker = tmp_path / "marker"
        root = tmp_path / name.replace("MARK", str(marker))

        _shell_output("cat /workspace/x.txt", root)

        assert not marker.exists()

    def test_the_real_root_the_model_typed_is_left_as_typed(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path, "My Docs")

        assert _rewrite(f"cd /workspace && ls '{root}'", root) == f"cd {shlex.quote(str(root))} && ls '{root}'"


class TestRootsGoingInAsTyped:
    @pytest.mark.parametrize("root", _PLAIN_ROOTS)
    @pytest.mark.parametrize("command", _COMMANDS_NAMING_THE_ROOT)
    def test_a_root_that_needs_no_quoting(self, root: str, command: str) -> None:
        assert _rewrite(command, root) == command.replace("/workspace", root)

    @pytest.mark.parametrize("command", ['printf "[%s]" "/workspace/x"', "printf '[%s]' '/workspace/x'"])
    def test_a_match_inside_quotes(self, command: str) -> None:
        assert _rewrite(command, "/tmp/My Docs") == command.replace("/workspace", "/tmp/My Docs")

    def test_a_heredoc_body_is_data(self, tmp_path: Path) -> None:
        root = _make_root(tmp_path, "My Docs")

        assert _shell_output("cat <<EOF\n/workspace/x.txt\nEOF\n", root) == f"{root}/x.txt\n"

    def test_a_non_posix_shell(self) -> None:
        assert _rewrite("ls /workspace/x", "/tmp/My Docs", posix_shell=False) == "ls /tmp/My Docs/x"
