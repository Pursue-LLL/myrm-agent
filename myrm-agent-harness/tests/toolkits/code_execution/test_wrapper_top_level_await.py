"""A script that awaits at module level runs with the semantics of plain execution.

The wrapper compiles user code with ``ast.PyCF_ALLOW_TOP_LEVEL_AWAIT`` instead of rewriting it
into an async function. Each test runs the real wrapper in a subprocess and checks a property
that a rewrite into a function changes: string literals, line numbers, module scope, ``return``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.common.wrapper_script import (
    ExecutionOutput,
    generate_wrapper_script,
    parse_execution_output,
)

# Two lines that make every script below a valid top-level-await script when followed by ``await one()``.
_ASYNC_ONE = "async def one():\n    return 1\n"


def _run(tmp_path: Path, user_code: str) -> ExecutionOutput:
    """Run *user_code* through the real wrapper in a subprocess and parse its JSON result."""
    code_file = tmp_path / "user_code.py"
    wrapper_file = tmp_path / "wrapper.py"
    code_file.write_text(user_code, encoding="utf-8")
    wrapper_file.write_text(generate_wrapper_script(str(code_file)), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(wrapper_file)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return parse_execution_output(proc.stdout, proc.stderr, proc.returncode)


class TestTopLevelAwaitKeepsPlainExecutionSemantics:
    def test_multiline_string_literal_is_not_reindented(self, tmp_path: Path) -> None:
        out = _run(tmp_path, _ASYNC_ONE + "await one()\nprint('''first\nsecond''')\n")
        assert out.success is True
        assert out.stdout == "first\nsecond\n"

    def test_traceback_names_the_scripts_own_line(self, tmp_path: Path) -> None:
        out = _run(tmp_path, _ASYNC_ONE + "await one()\nraise ValueError('boom')\n")
        assert out.success is False
        assert out.error == "ValueError: boom"
        assert 'File "<string>", line 4, in <module>' in out.stderr

    def test_global_statement_and_globals_see_module_names(self, tmp_path: Path) -> None:
        code = (
            "count = 0\n"
            "async def inc():\n    global count\n    count += 1\n"
            "await inc()\nawait inc()\n"
            "print(count, globals()['count'], __name__)\n"
        )
        out = _run(tmp_path, code)
        assert out.success is True
        assert out.stdout == "2 2 __main__\n"

    def test_builtin_name_can_be_rebound_after_use(self, tmp_path: Path) -> None:
        out = _run(tmp_path, _ASYNC_ONE + "await one()\nn = len([1, 2])\nlen = 5\nprint(n, len)\n")
        assert out.success is True
        assert out.stdout == "2 5\n"

    def test_star_import_is_allowed_after_an_await(self, tmp_path: Path) -> None:
        out = _run(tmp_path, _ASYNC_ONE + "await one()\nfrom os.path import *\nprint(basename('/a/b'))\n")
        assert out.success is True
        assert out.stdout == "b\n"

    @pytest.mark.parametrize(
        "user_code",
        ["x = await one()\nreturn x\n", "return 1\nx = await one()\n"],
        ids=["return_after_await", "return_before_await"],
    )
    def test_top_level_return_is_refused_wherever_it_appears(self, tmp_path: Path, user_code: str) -> None:
        out = _run(tmp_path, _ASYNC_ONE + user_code)
        assert out.success is False
        assert "'return' outside function" in (out.error or "")

    def test_syntax_error_in_a_script_that_awaits_is_reported_as_one(self, tmp_path: Path) -> None:
        out = _run(tmp_path, _ASYNC_ONE + "x = await one()\ny = (\n")
        assert out.success is False
        assert (out.error or "").startswith("SyntaxError: '(' was never closed")


class TestTopLevelAsyncConstructs:
    def test_async_comprehension(self, tmp_path: Path) -> None:
        code = "async def gen():\n    for i in range(3):\n        yield i\nprint([i async for i in gen()])\n"
        out = _run(tmp_path, code)
        assert out.success is True
        assert out.stdout == "[0, 1, 2]\n"

    def test_async_with_and_async_for(self, tmp_path: Path) -> None:
        code = (
            "import contextlib\n"
            "@contextlib.asynccontextmanager\n"
            "async def cm():\n    yield 'V'\n"
            "async def gen():\n    for i in range(2):\n        yield i\n"
            "async with cm() as v:\n    print('with', v)\n"
            "async for i in gen():\n    print('for', i)\n"
        )
        out = _run(tmp_path, code)
        assert out.success is True
        assert out.stdout == "with V\nfor 0\nfor 1\n"

    def test_future_import_header_is_honoured(self, tmp_path: Path) -> None:
        code = "from __future__ import annotations\nasync def f() -> int:\n    return 7\nprint(await f())\n"
        out = _run(tmp_path, code)
        assert out.success is True
        assert out.stdout == "7\n"
