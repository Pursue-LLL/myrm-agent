"""Runs a model-written script in an isolated Monty worker whose only reach into the browser is two session steps.

[INPUT]
- pydantic_monty (POS: Python interpreter in a worker process of its own; imported when a script runs, so an installation without its wheel keeps every other browser tool)
- exceptions::BrowserError (POS: root of the browser toolkit exception hierarchy)
- session.takeover::UserTakeoverDuringScriptError (POS: a script's next step comes after a person used the page it was planned against)
- semantic_dom_hitl::ScriptApprovalRequiredError (POS: a script's step needs a person's approval, which a script cannot ask for)

[OUTPUT]
- ScriptRejectedError: the script cannot run at all (a syntax error, an import, no statement, text that cannot be parsed); the message is what the model is told
- vet_script: the source Monty runs for a script (the text the model wrote, newlines normalized), unless a refusal applies to it
- BrowserSteps: the two session steps a script can take
- ScriptSession: what a script sees as `session`
- run_script: run the vetted script and return what it printed, followed by how it ended

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


def vet_script(script: str) -> str:
    """The source Monty runs: the script as the model wrote it, unless one of the refusals below applies.

    The tool description calls the script the body of `async def (session, refs)`. Monty runs it at the top level
    with `session` and `refs` bound, where `await` and `return` work as they do in such a body. Two corners differ:
    a helper function rebinds a name of the script with `global` (not `nonlocal`), and the script's first line must
    not be indented.

    A script is refused when it has a syntax error, when it has no statement (it is empty or has only comments, so
    it would report success for doing nothing), when the parser cannot take it at all, and when it imports. Imports
    are refused so that the description ("Imports and `open` are unavailable") stays true even for modules the
    interpreter would allow. Newlines are normalized the way the compiler reads them, so a carriage return inside a
    string reaches a step as a line feed.
    """
    source = io.StringIO(script, newline=None).read()  # \n, \r\n and \r each end one line
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ScriptRejectedError(f"SyntaxError in script: {exc.msg} (line {exc.lineno or 1})") from exc
    except (ValueError, MemoryError, RecursionError) as exc:
        # Text the parser cannot take at all: one that cannot be encoded (a lone surrogate), or one nested so deeply
        # that it gives up with RecursionError or, once its own stack is full, MemoryError
        raise ScriptRejectedError(f"[Error] The script cannot be parsed: {exc}") from exc
    if not tree.body:
        raise ScriptRejectedError("[Error] The script has no statements (it is empty or has only comments).")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise ScriptRejectedError(f"[Error] Imports are unavailable in scripts (line {node.lineno}).")
    return source


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
    """Run `code` (from `vet_script`) and return what it printed, followed by how it ended."""
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
