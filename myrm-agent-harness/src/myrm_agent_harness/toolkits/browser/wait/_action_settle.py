"""Post-action settle: wait for what the action just did to the page, not for the page to go quiet.

[INPUT]
- patchright.async_api::Page, Frame (POS: Patchright page instance and the frame of one of its documents)
- enhancers/dom_enhancer.js (POS: the page-side tracker that numbers fetch/XHR requests and marks where a user gesture began; it lives in the page's main world as ``window.__myrm_spa_state``)

[OUTPUT]
- settle_after_action: wait, within a cap, for the requests an action started to finish and for the page to draw them
- capped_note: the sentence an answer carries when that wait ended at its cap

[POS]
The wait an interaction ends with. A page is never quiet for good (polling, long-lived connections, animation), so
"wait until nothing is in flight" either returns at once or waits out the cap; what the answer needs is narrower: the
requests the action itself started. The tracker numbers every fetch/XHR and records the number reached when the
current input gesture began, so the requests to wait for are the pending ones numbered after that mark and anything
already in flight is ignored. Once they finish the page gets a short window to draw the response. A document the
tracker was not delivered to (a blank tab, a non-HTML document), an action that sent no input the tracker could see,
and a page that goes away mid-wait all end the wait at once, leaving the page as the action left it. Every document
has its own tracker, so the wait runs in the document the action's element lives in: the page, or the frame of an
iframe.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from patchright.async_api import Frame, Page

logger = logging.getLogger(__name__)

# The longest an action's answer is held back.
_DEFAULT_CAP_MS = 3000

# The handler of an input event may start its request a task later, so the page gets this long to do it.
_GRACE_MS = 30
# A response is drawn within this window of arriving; a page that keeps changing is not waited on past the limit.
_DRAW_QUIET_MS = 150
_DRAW_LIMIT_MS = 300
# Input older than this was not the action's: the action sent none the tracker could see.
_GESTURE_MAX_AGE_MS = 2000
# The page ends the wait itself at the cap; this is how long past it a page that cannot run script is given up on.
_ANSWER_SLACK_S = 1.0

# What an answer says when the wait hit the cap: the action happened, but the page had not finished answering it.
_CAPPED_NOTE = (
    " [The page was still loading the response to this action; what you read next may not show its result yet.]"
)

_SETTLE_JS = """({capMs, graceMs, quietMs, limitMs, gestureMaxAgeMs}) => new Promise((resolve) => {
    const state = window.__myrm_spa_state;
    const start = performance.now();
    if (!state || start - state.gestureTime > gestureMaxAgeMs) {
        resolve("untracked");
        return;
    }
    const mark = state.gestureSeq;
    const deadline = start + capMs;
    const outstanding = () => {
        for (const id of state.pending) {
            if (id > mark) return true;
        }
        return false;
    };
    const poll = () => {
        const now = performance.now();
        if (now >= deadline) {
            resolve("capped");
        } else if (outstanding()) {
            setTimeout(poll, 20);
        } else if (now >= Math.max(state.lastMutationTime, state.lastRequestEnd) + quietMs
                   || now >= state.lastRequestEnd + limitMs) {
            resolve("settled");
        } else {
            setTimeout(poll, 20);
        }
    };
    setTimeout(() => {
        if (state.requestSeq > mark) poll();
        else resolve("no_request");
    }, graceMs);
})"""


async def settle_after_action(target: Page | Frame, *, cap_ms: int = _DEFAULT_CAP_MS) -> str:
    """Wait, for at most ``cap_ms``, until the requests the action started are done and the page has drawn them.

    ``target`` is the page, or the frame of the iframe the action's element is in.

    Returns why the wait ended: ``settled`` (requests finished and drawn), ``no_request`` (the action asked for
    nothing), ``capped`` (still waiting at the cap), ``untracked`` (the page cannot tell, so nothing is waited for)
    or ``failed`` (the page could not be probed). It never raises: the action already happened, and a wait that
    cannot be carried out must not turn it into a failure.
    """
    arg = {
        "capMs": cap_ms,
        "graceMs": _GRACE_MS,
        "quietMs": _DRAW_QUIET_MS,
        "limitMs": _DRAW_LIMIT_MS,
        "gestureMaxAgeMs": _GESTURE_MAX_AGE_MS,
    }
    try:
        reason = await asyncio.wait_for(
            target.evaluate(_SETTLE_JS, arg, isolated_context=False), timeout=cap_ms / 1000 + _ANSWER_SLACK_S
        )
    except Exception as exc:
        logger.debug("Post-action settle skipped: %s", exc)
        return "failed"
    logger.debug("Post-action settle ended: %s", reason)
    return str(reason)


def capped_note(outcome: str) -> str:
    """The note to end an answer with when ``outcome`` says the wait hit its cap, otherwise nothing."""
    return _CAPPED_NOTE if outcome == "capped" else ""
