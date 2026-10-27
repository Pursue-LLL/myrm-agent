"""What the completion guard tells the outside when it holds an answer back: the event log and the stream.

A held-back answer costs one more model call and reaches the model as a request-only message, so nothing in the
conversation or the tool trace shows it. The event is how a trace tells why a turn took more model calls than the
answer needed; the status step tells the stream that the draft it just carried is superseded, so no consumer shows
or stores it next to the answer that replaces it.

[INPUT]
- agent.middlewares._session_context::get_event_logger (POS: the session's event logger, when one is configured)
- agent.middlewares.completion.completion_directive::BlockReasons (POS: why one completion attempt was held back)
- utils.event_utils::dispatch_custom_event (POS: puts a status step on the run's stream)

[OUTPUT]
- COMPLETION_GUARD_EVENT: the event type the guard's decisions are recorded under
- ANSWER_RECHECK_STEP: the status step key announcing a superseded draft
- log_guard_decision(): one event per held-back answer
- announce_superseded_draft(): the status step that carries the stream's restart signal

[POS]
The event carries names and counts only, never the request, the draft or the instruction text, so the log stays
free of user content; the status step carries no wording either, the UI words it in the user's language.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.middlewares._session_context import get_event_logger
from myrm_agent_harness.agent.middlewares.completion.completion_directive import BlockReasons
from myrm_agent_harness.utils.event_utils import dispatch_custom_event

logger = logging.getLogger(__name__)

COMPLETION_GUARD_EVENT = "completion_guard"
ANSWER_RECHECK_STEP = "answer_recheck"


async def log_guard_decision(reasons: BlockReasons, *, rejection: int, max_rejections: int) -> None:
    """Record that the guard held a draft back (or, past its budget, let the model finish with a warning)."""
    event_logger = get_event_logger()
    if event_logger is None:
        return
    await event_logger.log(
        COMPLETION_GUARD_EVENT,
        {
            "action": "forced_finish" if reasons.forced_finish else "held_back",
            "reasons": list(reasons.names()),
            "rejection": rejection,
            "max_rejections": max_rejections,
            "staged_artifacts": len(reasons.staged_artifacts),
        },
    )


async def announce_superseded_draft() -> None:
    """Tell the stream the draft just carried is superseded, so consumers drop it before the next answer streams.

    Best effort: a stream that cannot take the step must not change what the guard decides.
    """
    try:
        await dispatch_custom_event(
            "agent_status",
            {"step_key": ANSWER_RECHECK_STEP, "tool_name": None, "status": "warning", "restart": True},
        )
    except Exception:
        logger.debug("Could not announce the superseded draft", exc_info=True)
