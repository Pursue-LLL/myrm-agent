"""Deleting the root or the home directory is blocked wherever the operand ends.

``rm -rf /`` ends at the end of the line, but a shell ends an operand at a redirection, a comment, an escaped ``;``
of ``find -exec`` or a group closer just as well. The rules read the operand, not what happens to follow it.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import analyze_command, has_block_threat

_FLAGS = (
    "-rf",
    "-fr",
    "-r -f",
    "-Rf",
    "--recursive --force",
    "--force --recursive",
    "-f --recursive",
)
_ENDINGS = (
    "",
    " ",
    " > /dev/null 2>&1",
    " # clean up",
    ">log",
    ";ls",
    "&&ls",
    "|cat",
    " \\;",
    ")",
    " extra",
)


@pytest.mark.parametrize("ending", _ENDINGS)
@pytest.mark.parametrize("flags", _FLAGS)
@pytest.mark.parametrize("target", ["/", "~"])
def test_deleting_the_root_or_the_home_directory_is_blocked_whatever_follows_the_operand(
    target: str, flags: str, ending: str
) -> None:
    assert has_block_threat(f"rm {flags} {target}{ending}") is not None


def test_find_exec_that_deletes_the_root_is_blocked() -> None:
    assert has_block_threat("find . -exec rm -fr / \\;") is not None


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /tmp/build",
        "rm -fr /workspace/build",
        "rm -r -f build/",
        "rm -rf ./a /tmp/b",
        "rm -rf ../../",
        "rm --recursive --force /var/tmp/x",
        "rm -fr /.cache/pip > /dev/null",
        "rm -fr /\\;",
    ],
)
def test_deleting_a_path_below_the_root_is_not_deleting_the_root(command: str) -> None:
    assert not [t for t in analyze_command(command) if t.detail.startswith("Deleting root")]
