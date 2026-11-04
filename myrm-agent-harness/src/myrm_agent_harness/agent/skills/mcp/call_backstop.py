"""Outer time bound for one MCP tool call made by a script

[INPUT]
- (none)

[OUTPUT]
- BACKSTOP_MARGIN_SECONDS: How far above the configured ``execute_timeout`` the backstop sits.
- call_within_backstop: Await a tool call under the backstop; raise a named ``TimeoutError`` if it never answers.

[POS]
Each MCP session actor already ends a tool call at the server's ``execute_timeout`` and answers with a failure.
This bound exists for the actor that does not answer at all (a wedged connection), so the script gets a named
error instead of waiting for the host to kill it. It wraps the call alone, never the connect phase: a cold server
start has its own budget and is not part of a call that is within its limit.
"""

import asyncio
from collections.abc import Awaitable, Sequence

BACKSTOP_MARGIN_SECONDS = 10.0
"""Gap above the longest configured limit. The actor's own timeout, which carries the useful message, must fire first;
the host's kill (``execute_timeout`` + the host margin) must fire after."""


async def call_within_backstop[T](call: Awaitable[T], *, execute_timeouts: Sequence[float], label: str) -> T:
    """Await ``call``, bounded by the longest of ``execute_timeouts`` (non-empty) plus the margin.

    Only the backstop's own expiry is renamed; a ``TimeoutError`` raised by the call itself passes through unchanged.
    """
    backstop = max(execute_timeouts) + BACKSTOP_MARGIN_SECONDS
    scope = asyncio.timeout(backstop)
    try:
        async with scope:
            return await call
    except TimeoutError:
        if scope.expired():
            raise TimeoutError(f"MCP request to '{label}' timed out after {backstop:g}s") from None
        raise
