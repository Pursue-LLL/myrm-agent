"""Cancel-aware execution boundary for the browser tools.

[INPUT]
- utils.runtime.cancellation::run_until_cancelled, OperationCancelledError (POS: request-level cancellation token; run_until_cancelled is the boundary for operations that cannot observe it)
- session::BrowserSession (POS: browser session aggregate root; active_tab_crashed reads the browser's crash report for the active tab, recover_active_tab heals a page that stopped answering, take_tab_reset_notice tells the model about it, take_unannounced_downloads hands over the downloads no answer has carried yet)
- tools.download_actions::late_downloads_notice (POS: agent-facing text of the download actions)

[OUTPUT]
- apply_cancel_boundary: wrap every tool's coroutine in place so a stopped run releases the browser
- CANCELLED_RESULT: the result a tool returns when the run was stopped under it

[POS]
Cancel-aware execution boundary for the browser tools. Stopping a run only flips the request's
cancellation token. A browser action blocked inside the driver (a navigation to a server that
never answers, a script loop) never looks at that flag, so the tool would hold the session until
its own timeout. This boundary races each tool call against the token, aborts the call, heals the
tab and hands the model a plain result instead of an error. A run torn down from outside the
request (executor timeout, stuck-task watchdog, shutdown) cancels the tool without the token, and
nothing may call the session again soon, so the tab is healed there too before the cancellation
continues. A tab whose renderer the browser reported as crashed is healed before the call runs, so
no tool fails on (or answers from the cache of) a dead page. A healed tab is blank, so the next text
result carries the session's reset notice. A download a page started can settle after the action that
started it was answered, so the next text result also carries what it came to, once.
Mutates the tools it receives, because `with_dynamic_hints` already produced the final copies.
"""

from __future__ import annotations

import asyncio
import functools
from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, StructuredTool

from myrm_agent_harness.utils.runtime.cancellation import OperationCancelledError, run_until_cancelled

from .download_actions import late_downloads_notice

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ..session import BrowserSession

CANCELLED_RESULT = (
    "[cancelled] The run was stopped while this browser action was in progress, so it may have been "
    "only partially applied. Inspect the page before relying on its state."
)


def apply_cancel_boundary(tools: list[BaseTool], session: BrowserSession) -> list[BaseTool]:
    """Make every tool in `tools` abort promptly when the current run is stopped.

    Raises:
        TypeError: a tool has no coroutine to guard (it would silently stay uncancellable).
    """
    for tool in tools:
        if not isinstance(tool, StructuredTool) or tool.coroutine is None:
            raise TypeError(f"Cannot guard {tool.name}: it has no coroutine")
        tool.coroutine = _cancel_aware(tool.coroutine, session)
    return tools


def _cancel_aware(
    coroutine: Callable[..., Awaitable[object]], session: BrowserSession
) -> Callable[..., Awaitable[object]]:
    @functools.wraps(coroutine)
    async def run(*args: object, **kwargs: object) -> object:
        if session.active_tab_crashed():
            await session.recover_active_tab()
        try:
            result = await run_until_cancelled(coroutine(*args, **kwargs))
        except OperationCancelledError:
            await session.recover_active_tab()
            return CANCELLED_RESULT
        except asyncio.CancelledError:
            await session.recover_active_tab()
            raise
        return _with_pending_notices(result, session)

    return run


def _with_pending_notices(result: object, session: BrowserSession) -> object:
    """Add what the model has not been told yet to a text result: the tab reset ahead of it, late downloads after it.

    Other results leave the notices pending.
    """
    if not isinstance(result, str):
        return result
    reset = session.take_tab_reset_notice()
    if reset is not None:
        result = f"{reset}\n\n{result}"
    if late_downloads := late_downloads_notice(session.take_unannounced_downloads()):
        result = f"{result}\n\n{late_downloads}"
    return result
