"""A model-written script runs in an isolated worker: it reaches the browser through two steps and nothing else."""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.session.takeover import UserTakeoverDuringScriptError
from myrm_agent_harness.toolkits.browser.snapshot.aria_types import RefInfo
from myrm_agent_harness.toolkits.browser.tools import script_runtime
from myrm_agent_harness.toolkits.browser.tools.script_runtime import ScriptRejectedError, run_script, wrap_script
from myrm_agent_harness.toolkits.browser.tools.semantic_dom_hitl import (
    ScriptApprovalRequiredError,
    enforce_semantic_interaction_guard,
)
from myrm_agent_harness.utils.runtime.user_control import planned_against

_REFS: dict[str, dict[str, str | int | None]] = {"e1": {"role": "button", "name": "OK", "nth": 0}}
_CANARY = "canary-value-do-not-leak"
_HOST_SECRET = "host-secret-do-not-leak"


class _Steps:
    """A browser session reduced to the two steps a script can take, recording what reached it."""

    secret = _HOST_SECRET

    def __init__(
        self, *, fail_at: dict[int, Exception] | None = None, slow_ref: str | None = None, delay_s: float = 0.0
    ) -> None:
        self.calls: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self._fail_at = fail_at or {}
        self._slow_ref = slow_ref
        self._delay_s = delay_s

    async def interact(self, action: str, ref: str, text: str = "") -> str:
        self.calls.append(("interact", ref))
        if (error := self._fail_at.get(len(self.calls))) is not None:
            raise error
        if ref == self._slow_ref:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                self.cancelled.append(ref)
                raise
        return f"ok {action} {ref}"

    async def evaluate(self, expression: str) -> str:
        self.calls.append(("evaluate", expression))
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        return f"value of {expression}"


async def _run(script: str, steps: _Steps | None = None, *, timeout_s: float = 30.0) -> tuple[str, list[str]]:
    """What the script returned and the progress messages it produced."""
    progress: list[str] = []

    async def report(message: str) -> None:
        progress.append(message)

    return await run_script(
        steps or _Steps(), wrap_script(script), _REFS, timeout_s=timeout_s, progress=report
    ), progress


class TestTheScriptContract:
    @pytest.mark.asyncio
    async def test_the_script_is_the_body_of_an_async_function_that_prints_its_result(self) -> None:
        steps = _Steps()
        script = "print(await session.interact('click', 'e1'))\nprint(refs['e1']['role'], refs['e1']['name'])\nreturn"

        result, _ = await _run(script, steps)

        assert result == "ok click e1\nbutton OK\n"
        assert steps.calls == [("interact", "e1")]

    @pytest.mark.asyncio
    async def test_a_script_can_evaluate_javascript_through_the_session(self) -> None:
        steps = _Steps()

        result, _ = await _run("print(await session.evaluate('document.title'))", steps)

        assert result == "value of document.title\n"
        assert steps.calls == [("evaluate", "document.title")]

    @pytest.mark.asyncio
    async def test_prints_before_a_step_are_reported_as_progress_and_the_rest_is_the_result(self) -> None:
        script = "print('before')\nawait session.interact('click', 'e1')\nprint('after')"

        result, progress = await _run(script)

        assert progress == ["[Script] before"]
        assert result == "before\nafter\n"

    @pytest.mark.asyncio
    async def test_a_step_error_reaches_the_script_with_its_message(self) -> None:
        steps = _Steps(fail_at={1: RuntimeError("Ref e9 not found. Take a new snapshot.")})
        script = "try:\n    await session.interact('click', 'e9')\nexcept Exception as e:\n    print('caught:', e)"

        result, _ = await _run(script, steps)

        assert result == "caught: Ref e9 not found. Take a new snapshot.\n"

    @pytest.mark.asyncio
    async def test_a_step_error_the_script_does_not_catch_is_reported_with_where_it_happened(self) -> None:
        steps = _Steps(fail_at={1: RuntimeError("Ref e9 not found.")})

        result, _ = await _run("x = 1\nawait session.interact('click', 'e9')", steps)

        assert "[Error] Runtime exception" in result
        assert "Ref e9 not found." in result
        assert "await session.interact('click', 'e9')" in result

    @pytest.mark.asyncio
    async def test_a_script_that_prints_nothing_returns_nothing(self) -> None:
        result, _ = await _run("x = 1")

        assert result == ""

    @pytest.mark.parametrize(
        "script",
        ["x = 1\ndef foo(:", 'x = 1\ny = """abc', "x = 1\ny = (\n  1,"],
        ids=["syntax-error", "unterminated-string", "unclosed-bracket"],
    )
    def test_a_syntax_error_is_rejected_with_the_line_of_the_script(self, script: str) -> None:
        with pytest.raises(ScriptRejectedError, match=r"^SyntaxError in script: .* \(line 2\)$"):
            wrap_script(script)

    @pytest.mark.parametrize("script", ["import os", "from os import path", "x = 1\nif x:\n    import json"])
    def test_imports_are_refused_before_anything_runs(self, script: str) -> None:
        with pytest.raises(ScriptRejectedError, match=r"^\[Error\] Imports are unavailable in scripts \(line \d\)\.$"):
            wrap_script(script)

    @pytest.mark.parametrize(
        "script",
        [
            pytest.param('x = """a\n  b\nc"""', id="triple-quoted"),
            pytest.param('x = r"""a\\n\n  b"""', id="raw-triple-quoted"),
            pytest.param('v = 1\nx = f"""a {v}\n  b {v}"""', id="f-string"),
            pytest.param('v = 1\nx = f"{\nv=}"', id="f-string-debug-field-across-lines"),
            pytest.param('x = "a\\\n  b"', id="backslash-continued"),
            pytest.param("if True:\n\tx = '''a\n\t  b'''", id="tab-indented"),
            pytest.param("x = '''a\r\n  b'''\r\ny = 1", id="crlf"),
            pytest.param("x = '''a\rb'''\ry = 1", id="lone-cr"),
            pytest.param('x = "a\u2028b"', id="unicode-line-separator"),
            pytest.param('x = "a\x0cb"', id="form-feed"),
            pytest.param("\x0cx = 1", id="leading-form-feed"),
            pytest.param("if True:\n  \x0c  x = 1", id="form-feed-inside-indentation"),
        ],
    )
    def test_the_body_of_the_wrapper_means_what_the_script_means_on_its_own(self, script: str) -> None:
        wrapped = ast.parse(wrap_script(script)).body[0]
        alone = compile(script, "<script>", "exec", flags=ast.PyCF_ONLY_AST | ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)

        assert isinstance(wrapped, ast.AsyncFunctionDef)
        assert ast.dump(ast.Module(wrapped.body, [])) == ast.dump(alone)

    @pytest.mark.asyncio
    async def test_a_multi_line_string_reaches_the_step_as_it_was_written(self) -> None:
        steps = _Steps()

        await _run('await session.evaluate("""(() => {\n  return 1\n})()""")', steps)

        assert steps.calls == [("evaluate", "(() => {\n  return 1\n})()")]


class TestLimits:
    @pytest.mark.asyncio
    async def test_the_time_limit_cancels_the_step_that_is_still_running(self) -> None:
        steps = _Steps(slow_ref="slow")

        result, _ = await _run(
            "await session.interact('click', 'slow')\nawait session.interact('click', 'after')", steps, timeout_s=0.5
        )

        assert "timed out" in result
        assert steps.cancelled == ["slow"], (
            "a step left running would act on the page after the script was reported over"
        )
        assert steps.calls == [("interact", "slow")]

    @pytest.mark.asyncio
    async def test_a_script_that_spins_is_ended_by_the_cpu_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(script_runtime, "_CPU_LIMIT_S", 0.5)

        result, _ = await _run("while True:\n    pass", timeout_s=30)

        assert "TimeoutError" in result
        assert "timed out after" not in result, "the interpreter's own limit ended it long before the wall clock"

    @pytest.mark.asyncio
    async def test_the_cpu_limit_does_not_count_the_time_a_step_waits_on_the_browser(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(script_runtime, "_CPU_LIMIT_S", 0.3)

        result, _ = await _run("print(await session.evaluate('x'))", _Steps(delay_s=1.0))

        assert result == "value of x\n"

    @pytest.mark.asyncio
    async def test_a_script_that_allocates_without_end_is_ended_by_the_memory_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(script_runtime, "_MEMORY_LIMIT_BYTES", 8 * 1024 * 1024)

        result, _ = await _run("xs = []\nfor i in range(10_000_000):\n    xs.append('x' * 1000)")

        assert "MemoryError" in result

    @pytest.mark.asyncio
    async def test_a_script_that_prints_without_end_returns_a_capped_result_that_says_so(self) -> None:
        result, _ = await _run("for i in range(200_000):\n    print('x' * 50)")

        limit = script_runtime._OUTPUT_LIMIT_CHARS
        assert result.startswith("x" * 50 + "\n")
        assert len(result) == limit + len(script_runtime._TRUNCATED)
        assert result.endswith(script_runtime._TRUNCATED)

    @pytest.mark.asyncio
    async def test_a_huge_error_message_is_capped_too(self) -> None:
        result, _ = await _run("raise Exception('y' * 100_000)")

        assert len(result) <= script_runtime._OUTPUT_LIMIT_CHARS + len(script_runtime._TRUNCATED) + 1


class TestAScriptThatMustStop:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error", "told"),
        [
            (UserTakeoverDuringScriptError(), "a person used the browser while it was running"),
            (ScriptApprovalRequiredError("destructive action"), "a step needs a person's approval"),
        ],
    )
    async def test_a_stop_the_script_swallows_still_ends_it_and_is_reported(self, error: Exception, told: str) -> None:
        steps = _Steps(fail_at={2: error})
        script = (
            "for ref in ['a', 'b', 'c']:\n"
            "    try:\n"
            "        await session.interact('click', ref)\n"
            "        print('ok', ref)\n"
            "    except Exception:\n"
            "        print('swallowed', ref)\n"
        )

        result, _ = await _run(script, steps)

        assert steps.calls == [("interact", "a"), ("interact", "b")], "no step may reach the page after the stop"
        assert result.startswith("ok a\nswallowed b\nswallowed c\n")
        assert told in result
        assert "already ran" in result

    @pytest.mark.asyncio
    async def test_any_other_step_error_leaves_the_script_free_to_go_on(self) -> None:
        steps = _Steps(fail_at={2: RuntimeError("element is covered")})
        script = (
            "for ref in ['a', 'b', 'c']:\n"
            "    try:\n"
            "        await session.interact('click', ref)\n"
            "    except Exception as e:\n"
            "        print('failed', ref, e)\n"
        )

        result, _ = await _run(script, steps)

        assert [ref for _, ref in steps.calls] == ["a", "b", "c"]
        assert result == "failed b element is covered\n"

    @pytest.mark.asyncio
    async def test_a_high_risk_step_in_a_plan_stops_the_script_without_asking_a_person(self) -> None:
        """The gate runs inside the host step: the plan it checks must reach it through the worker's callback."""
        page_source = MagicMock()
        page_source.get_active_page.return_value.url = "https://shop.test/account"

        class _GatedSteps(_Steps):
            async def interact(self, action: str, ref: str, text: str = "") -> str:
                self.calls.append(("interact", ref))
                blocked = await enforce_semantic_interaction_guard(
                    session=page_source,
                    tool_name="browser_execute_script_tool",
                    action=action,
                    ref=ref,
                    ref_info=RefInfo(role="button", name="Delete account", nth=None),
                )
                return blocked or f"ok {action} {ref}"

        steps = _GatedSteps()
        with patch("langgraph.types.interrupt") as interrupt, planned_against(0):
            result, _ = await _run("print('start')\nawait session.interact('click', 'e5')\nprint('unreachable')", steps)

        interrupt.assert_not_called()
        assert "a step needs a person's approval" in result
        assert "Delete account" in result
        assert "unreachable" not in result


_ESCAPES = {
    "mro-subclasses": "print(().__class__.__mro__[1].__subclasses__())",
    "list-class-base": "print([].__class__.__base__.__subclasses__())",
    "str-mro": "print(''.__class__.__mro__)",
    "type-session-mro": "print(type(session).__mro__)",
    "session-dict": "print(session.__dict__)",
    "interact-func": "print(session.interact.__func__)",
    "interact-self": "print(session.interact.__self__)",
    "lambda-globals": "print((lambda: 0).__globals__)",
    "lambda-code": "print((lambda: 0).__code__)",
    "gen-frame": "print((x for x in []).gi_frame.f_back)",
    "builtins-name": "print(__builtins__)",
    "globals-call": "print(globals())",
    "vars-session": "print(vars(session))",
    "format-class": "print('{0.__class__.__init__.__globals__}'.format(session))",
    "format-func": "print('{0.__globals__}'.format(lambda: 0))",
    "dunder-import": "print(__import__('os').environ)",
    "import-os-environ": "import os\nprint(os.environ)",
    "import-subprocess": "import subprocess\nsubprocess.run(['id'])",
    "import-socket": "import socket\nprint(socket.gethostname())",
    "open-write": "open('{marker}', 'w').write('x')",
    "exec-os-getpid": "exec('import os; print(os.getpid())')",
    "exec-os-environ": "exec('import os\\nprint(dict(os.environ))')",
    "exec-os-getenv": "exec('import os\\nprint(os.getenv(\"SCRIPT_TEST_CANARY\"))')",
    "exec-os-listdir": "exec('import os\\nprint(os.listdir(\"/\"))')",
    "eval-subclasses": "print(eval('().__class__.__base__.__subclasses__()'))",
    "call-undeclared-host": "print(session.secret())",
    "read-host-attribute": "print(session._steps.secret)",
    "private-steps": "print(session._steps)",
    "private-inflight": "print(session._inflight)",
    "cancel-inflight": "await session.cancel_inflight()",
    "stop-slot": "print(session.stopped_by)",
    "asyncio-subprocess": (
        "p = await asyncio.create_subprocess_exec('echo', 'rce-' + 'marker', stdout=asyncio.subprocess.PIPE)\n"
        "out, _ = await p.communicate()\nprint(out.decode().strip())"
    ),
    "subclasses-to-os-environ": (
        "print([c for c in ().__class__.__base__.__subclasses__() if c.__name__ == 'catch_warnings'][0]"
        ".__init__.__globals__['sys'].modules['os'].environ.get('SCRIPT_TEST_CANARY'))"
    ),
    "format-to-environ": "print('{0.interact.__func__.__globals__[logging].os.environ[SCRIPT_TEST_CANARY]}'.format(session))",
}


class TestIsolationFromTheHost:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", list(_ESCAPES))
    async def test_no_way_out_of_the_interpreter_to_the_host(
        self, name: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SCRIPT_TEST_CANARY", _CANARY)
        marker = tmp_path / "written-by-the-script"
        script = _ESCAPES[name].replace("{marker}", str(marker))

        try:
            result, _ = await _run(script)
        except ScriptRejectedError as rejected:
            result = str(rejected)

        assert "[Error]" in result, f"{name} ran: {result!r}"
        for leaked in (_CANARY, _HOST_SECRET, "rce-marker", "uid="):
            assert leaked not in result, f"{name} leaked {leaked!r}"
        assert not marker.exists()

    @pytest.mark.asyncio
    async def test_the_session_a_script_holds_is_a_proxy_that_names_no_host_class(self) -> None:
        result, _ = await _run("print(getattr(session, '__class__'))")

        assert result == "<class 'ScriptSession'>\n"


class TestWhenTheRuntimeCannotRun:
    @pytest.mark.asyncio
    async def test_without_the_wheel_the_script_is_not_run_by_the_host_interpreter(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "pydantic_monty", None)
        steps = _Steps()

        result, _ = await _run("print('ran')\nawait session.interact('click', 'e1')", steps)

        assert result == script_runtime._UNAVAILABLE
        assert steps.calls == []

    @pytest.mark.asyncio
    async def test_a_worker_that_cannot_start_is_reported_the_same_way(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("MONTY_BIN", str(tmp_path / "no-such-worker"))
        steps = _Steps()

        result, _ = await _run("await session.interact('click', 'e1')", steps)

        assert result == script_runtime._UNAVAILABLE
        assert steps.calls == []
