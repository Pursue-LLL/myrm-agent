"""A foreground command reads an empty stdin, through the real bash tool and a real shell.

A command in the persistent shell reads end of file at once: it cannot take the commands that end it off the pipe
carrying them, so the shell is not killed and does not wait out its timeout. Every case runs while the host's stdin
is a pipe that never ends, as it is for a host started from a terminal or a desktop shell.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator

import pytest

from tests.agent.meta_tools.bash.real_stack import RealBashStack

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

_TIMEOUT = 5


@pytest.fixture(autouse=True)
def _host_stdin_never_ends() -> Iterator[None]:
    """Make fd 0 a pipe whose writer stays open: it never gives data and never gives end of file."""
    read_fd, write_fd = os.pipe()
    saved = os.dup(0)
    os.dup2(read_fd, 0)
    try:
        yield
    finally:
        os.dup2(saved, 0)
        for fd in (saved, read_fd, write_fd):
            os.close(fd)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param("cat", "", id="cat"),
        pytest.param('read -r line\necho "got:[$line]"', "got:[]", id="read"),
        pytest.param("wc -l", "0", id="wc"),
        pytest.param("head -1", "", id="head"),
    ],
)
async def test_a_command_that_reads_stdin_gets_end_of_file_and_the_next_call_runs(
    shared_real_stack: RealBashStack, command: str, expected: str
) -> None:
    output = await shared_real_stack.run(command, timeout=_TIMEOUT)

    assert expected in output
    assert "alive" in await shared_real_stack.run("echo alive", timeout=_TIMEOUT)


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param("printf 'a\\nb\\n' | wc -l", "2", id="pipe"),
        pytest.param("cat <<'EOF'\nfrom-heredoc\nEOF", "from-heredoc", id="heredoc"),
        pytest.param("printf 'from-file\\n' > in.txt\ncat < in.txt", "from-file", id="redirect"),
    ],
)
async def test_input_a_command_names_itself_still_reaches_it(
    shared_real_stack: RealBashStack, command: str, expected: str
) -> None:
    assert expected in await shared_real_stack.run(command, timeout=_TIMEOUT)
