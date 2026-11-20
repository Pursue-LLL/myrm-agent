"""Runs a model-written script in an isolated Monty worker whose only reach into the browser is two session steps.

[INPUT]
- pydantic_monty (POS: Python interpreter in a worker process of its own; imported when a script runs, so an installation without its wheel keeps every other browser tool)
- exceptions::BrowserError (POS: root of the browser toolkit exception hierarchy)
- session.takeover::UserTakeoverDuringScriptError (POS: a script's next step comes after a person used the page it was planned against)
- semantic_dom_hitl::ScriptApprovalRequiredError (POS: a script's step needs a person's approval, which a script cannot ask for)

[OUTPUT]
- ScriptRejectedError: the script cannot run at all (a syntax error, an import); the message is what the model is told
- wrap_script: the source Monty runs for a script body (its multi-line strings keep the text the model wrote), after the checks the tool contract states
- BrowserSteps: the two session steps a script can take
- ScriptSession: what a script sees as `session`
- run_script: run the wrapped script and return what it printed, followed by how it ended

[POS]
Isolation boundary of browser_execute_script_tool. A script runs in a Monty worker process, never in the host
interpreter: it has its own heap, no filesystem, no network and no host objects. `session` inside it is a
`ScriptSession` exposing `interact` and `evaluate` only, so neither the browser session nor the Playwright page
behind it can be reached. The isolation is the interpreter's (a language-level sandbox), not the operating
system's; the worker runs as the same user as the host. Wall time, worker CPU time, worker memory and output size
are bounded, and a script that ends early leaves no step running.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import logging
import textwrap
import tokenize
from collections.abc import Awaitable, Callable
from typing import Protocol

from ..exceptions import BrowserError
from ..session.takeover import UserTakeoverDuringScriptError
from .semantic_dom_hitl import ScriptApprovalRequiredError

logger = logging.getLogger(__name__)

# A script that spins, allocates or prints without end ends with an error instead of costing the agent's
# resources. The CPU clock pauses while a step waits on the browser, so slow pages do not count against it.
_CPU_LIMIT_S = 5.0
_MEMORY_LIMIT_BYTES = 64 * 1024 * 1024
_OUTPUT_LIMIT_CHARS = 20_000
_TRUNCATED = f"\n[Output truncated at {_OUTPUT_LIMIT_CHARS} characters]"

_ENTRY = "_agent_step"
_BODY_INDENT = "    "
_STEP_NAMES = ("interact", "evaluate")

_UNAVAILABLE = (
    "[Error] The script runtime is not available in this installation. "
    "Run the steps one at a time with browser_interact_tool (its steps[] runs several in one call)."
)


class ScriptRejectedError(Exception):
    """The script cannot run at all; the message is what the model is told."""


class BrowserSteps(Protocol):
    """The two session steps a script can take; BrowserSession provides both."""

    async def interact(self, action: str, ref: str, text: str = "") -> str: ...

    async def evaluate(self, expression: str) -> str: ...


def wrap_script(script: str) -> str:
    """The source Monty runs: the script as the body of `async def (session, refs)`, then a call of it.

    Imports are refused here so that the tool description ("Imports and `open` are unavailable") stays true
    even for modules the interpreter would allow.
    """
    wrapped = f"async def {_ENTRY}(session, refs):\n{_indent_body(script)}\n"
    try:
        tree = ast.parse(wrapped)
    except SyntaxError as exc:
        raise ScriptRejectedError(f"SyntaxError in script: {exc.msg} (line {_script_line(exc.lineno)})") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise ScriptRejectedError(f"[Error] Imports are unavailable in scripts (line {_script_line(node.lineno)}).")
    return f"{wrapped}await {_ENTRY}(session, refs)\n"


def _indent_body(script: str) -> str:
    """The script's lines indented into the function body, except those inside a multi-line string.

    Indenting a line that continues a string would change the string, and with it what a step receives
    (a JavaScript snippet in a triple-quoted string, for one). An f-string counts as a whole, because the `=`
    of `f"{x=}"` prints the field's source text, spaces included.
    """
    source = io.StringIO(script, newline=None).read()  # the newlines the compiler reads: \n, \r\n and \r
    inside_token: set[int] = set()
    open_fstrings: list[int] = []  # the line each f-string still open began on
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            first_line = token.start[0]
            if token.type == tokenize.FSTRING_START:
                open_fstrings.append(first_line)
            elif token.type == tokenize.FSTRING_END:
                first_line = open_fstrings.pop()
            inside_token.update(range(first_line + 1, token.end[0] + 1))
    except (tokenize.TokenError, SyntaxError, ValueError):
        # Not tokenizable (a ValueError is text that cannot be encoded, a lone surrogate for one): `ast.parse`
        # judges it next, exactly as it would the text indented as a whole.
        return textwrap.indent(script, _BODY_INDENT)
    return "\n".join(
        line if number in inside_token or not line.strip() else _indent_line(line)
        for number, line in enumerate(source.split("\n"), 1)
    )


def _indent_line(line: str) -> str:
    """`line` moved into the function body; Python counts a line's indentation from its last leading form feed."""
    blank = line[: len(line) - len(line.lstrip(" \t\f"))]
    cut = blank.rfind("\f") + 1
    return line[:cut] + _BODY_INDENT + line[cut:]


def _script_line(wrapped_line: int | None) -> int:
    """A line of the wrapped source as the line of the script the model wrote (the `async def` takes line 1)."""
    return max((wrapped_line or 2) - 1, 1)


def _clip(text: str) -> str:
    return text if len(text) <= _OUTPUT_LIMIT_CHARS else text[:_OUTPUT_LIMIT_CHARS] + _TRUNCATED


class _Output:
    """What the script printed (capped), and how much of it has been reported as progress."""

    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._size = 0
        self._reported = 0
        self._truncated = False

    def write(self, _stream: str, text: str) -> None:
        """Monty's print callback; it is called one chunk at a time from the pool's reader thread."""
        kept = text[: max(_OUTPUT_LIMIT_CHARS - self._size, 0)]
        if kept:
            self._chunks.append(kept)
            self._size += len(kept)
        self._truncated = self._truncated or len(kept) < len(text)

    def unreported(self) -> str:
        """The text printed since the last call (Monty hands over a script's prints before each of its steps)."""
        end = len(self._chunks)
        text = "".join(self._chunks[self._reported : end])
        self._reported = end
        return text

    def text(self) -> str:
        return "".join(self._chunks) + (_TRUNCATED if self._truncated else "")


class ScriptSession:
    """What a script sees as `session`: the two browser steps, each tracked so a script that ends leaves none running."""

    def __init__(self, steps: BrowserSteps, output: _Output, progress: Callable[[str], Awaitable[None]]) -> None:
        self._steps = steps
        self._output = output
        self._progress = progress
        self._inflight: set[asyncio.Task[object]] = set()
        self.stopped_by: BrowserError | None = None

    async def interact(self, action: str, ref: str, text: str = "") -> str:
        return await self._step(lambda: self._steps.interact(action, ref, text))

    async def evaluate(self, expression: str) -> str:
        return await self._step(lambda: self._steps.evaluate(expression))

    async def _step(self, run: Callable[[], Awaitable[str]]) -> str:
        if self.stopped_by is not None:
            raise self.stopped_by
        if printed := self._output.unreported():
            with contextlib.suppress(Exception):
                await self._progress(f"[Script] {printed.rstrip()}")
        task = asyncio.current_task()
        if task is not None:
            self._inflight.add(task)
        try:
            return await run()
        except BrowserError as exc:
            # These two end the script: whatever the script does with the error, it must not reach the page again.
            if isinstance(exc, UserTakeoverDuringScriptError | ScriptApprovalRequiredError):
                self.stopped_by = exc
            raise
        finally:
            if task is not None:
                self._inflight.discard(task)

    async def cancel_inflight(self) -> None:
        """Cancel the steps still running: Monty leaves a step it handed to the host running when it cuts a script off."""
        current = asyncio.current_task()
        pending = [task for task in self._inflight if task is not current]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def run_script(
    steps: BrowserSteps,
    code: str,
    refs: dict[str, dict[str, str | int | None]],
    *,
    timeout_s: float,
    progress: Callable[[str], Awaitable[None]],
) -> str:
    """Run `code` (from `wrap_script`) and return what it printed, followed by how it ended."""
    try:
        import pydantic_monty as monty
    except ImportError as exc:
        logger.warning("Browser scripts cannot run: pydantic-monty is not installed (%s)", exc)
        return _UNAVAILABLE

    output = _Output()
    session = ScriptSession(steps, output, progress)
    ending = ""
    async with contextlib.AsyncExitStack() as stack:
        try:
            pool = await stack.enter_async_context(monty.AsyncMonty())
            sandbox = await stack.enter_async_context(
                pool.checkout(limits={"max_feed_duration_secs": _CPU_LIMIT_S, "max_memory": _MEMORY_LIMIT_BYTES})
            )
        except (OSError, RuntimeError, monty.MontyError):
            logger.error("The Monty worker could not start: browser scripts cannot run", exc_info=True)
            return _UNAVAILABLE
        try:
            await asyncio.wait_for(
                sandbox.feed_run(
                    code,
                    inputs={"session": monty.ClassInstance(session, allowed_methods=_STEP_NAMES), "refs": refs},
                    print_callback=output.write,
                ),
                timeout=timeout_s,
            )
        except TimeoutError:
            ending = f"[Error] Script execution timed out after {timeout_s:.0f} seconds."
        except monty.MontyRuntimeError as exc:
            ending = f"[Error] Runtime exception:\n{exc.display()}"
        except monty.MontyError as exc:
            ending = f"[Error] The script could not be run: {exc}"
        finally:
            await session.cancel_inflight()

    if session.stopped_by is not None:
        ending = str(session.stopped_by)
    return f"{output.text()}\n{_clip(ending)}" if ending else output.text()
