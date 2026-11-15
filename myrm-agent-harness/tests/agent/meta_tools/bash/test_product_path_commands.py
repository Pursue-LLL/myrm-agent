"""Shell commands the bash tool must hand to the shell as written, run through the real tool and a real shell.

Each case is a command a model writes every day: a heredoc that writes a data file leaves that file, and a redirect
to ``/dev/null`` runs. The outcome depends on the router, the path guard and the shell together, which a unit test
of one layer cannot see.
"""

from __future__ import annotations

import sys

import pytest

from myrm_agent_harness.utils.errors import ToolError
from tests.agent.meta_tools.bash.real_stack import RealBashStack

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell semantics")

# Texts that also parse as Python: a dict, ``KEY=1`` lines and bare names are all valid expressions.
_FILE_WRITES = [
    pytest.param("data.json", "cat > data.json <<'EOF'\n{\"a\": 1}\nEOF", '{"a": 1}\n', id="json"),
    pytest.param(
        "settings.ini", "cat > settings.ini <<'EOF'\nDEBUG=True\nWORKERS=4\nEOF", "DEBUG=True\nWORKERS=4\n", id="ini"
    ),
    pytest.param("notes.txt", "cat > notes.txt <<'EOF'\nhello\nworld\nEOF", "hello\nworld\n", id="txt"),
    pytest.param(
        "requirements.txt", "cat > requirements.txt <<'EOF'\nnumpy\npandas\nEOF", "numpy\npandas\n", id="requirements"
    ),
    pytest.param("cfg.json", "cat <<'EOF' > cfg.json\n{\"k\": [1, 2]}\nEOF", '{"k": [1, 2]}\n', id="marker-first"),
    pytest.param(
        "sub/data.json", "mkdir -p sub && cat > sub/data.json <<'EOF'\n{\"a\": 1}\nEOF", '{"a": 1}\n', id="after-mkdir"
    ),
]


@pytest.mark.parametrize(("name", "command", "content"), _FILE_WRITES)
async def test_a_heredoc_write_of_a_non_python_file_leaves_that_file(
    shared_real_stack: RealBashStack, name: str, command: str, content: str
) -> None:
    await shared_real_stack.run(command)

    assert (shared_real_stack.workspace / name).read_text() == content


async def test_a_heredoc_write_of_a_python_script_still_runs_it(shared_real_stack: RealBashStack) -> None:
    output = await shared_real_stack.run("cat > job.py <<'EOF'\nprint('py-ran', 6 * 7)\nEOF\npython3 job.py")

    assert "py-ran 42" in output


async def test_a_heredoc_write_of_an_env_file_is_still_refused(shared_real_stack: RealBashStack) -> None:
    with pytest.raises(ToolError, match="protected file"):
        await shared_real_stack.run("cat > .env <<'EOF'\nPORT=8080\nEOF")

    assert not (shared_real_stack.workspace / ".env").exists()


@pytest.mark.parametrize(
    ("command", "expected", "absent"),
    [
        pytest.param("echo shown && echo hidden > /dev/null", "shown", "hidden", id="stdout"),
        pytest.param(
            "ls no-such-entry 2> /dev/null || echo quiet-failure", "quiet-failure", "No such file", id="stderr"
        ),
        pytest.param("ls no-such-entry > /dev/null 2>&1 || echo gone", "gone", "No such file", id="both"),
        pytest.param("cat < /dev/null && echo eof-ok", "eof-ok", "", id="source"),
    ],
)
async def test_a_dev_null_redirect_is_run_not_refused(
    shared_real_stack: RealBashStack, command: str, expected: str, absent: str
) -> None:
    output = await shared_real_stack.run(command)

    assert expected in output
    assert not absent or absent not in output


async def test_a_path_outside_the_workspace_is_still_refused(shared_real_stack: RealBashStack) -> None:
    with pytest.raises(ToolError, match="Access denied: /etc"):
        await shared_real_stack.run("ls /etc > /dev/null")
