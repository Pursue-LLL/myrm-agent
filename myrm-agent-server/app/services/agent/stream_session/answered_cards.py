"""Settle the stored clarification card a finished run answered.

[INPUT]
- app.services.agent.stream_session.stream_session_types::AgentStreamSession (POS: request resume value and collector state)
- app.services.agent.streaming_support.hitl_timeout::mark_pending_clarification_answered (POS: flip the newest unanswered stored card)

[OUTPUT]
- settle_answered_cards: mark the answered card done and keep how it was answered on it

[POS]
Finalize step of a turn that resumed from a clarification interrupt, or whose Deep Research clarify phase
resolved. The card lives on an earlier assistant row; the answer is recorded on it so the transcript still shows it.
"""

from __future__ import annotations

from app.services.agent.stream_session.stream_session_types import AgentStreamSession
from app.services.agent.streaming_support.hitl_timeout import (
    HitlAnswerRecord,
    mark_pending_clarification_answered,
)


async def settle_answered_cards(session: AgentStreamSession) -> None:
    """Close the stored card this run answered and keep how it was answered on the card.

    Runs before the continuation is persisted: the continuation may carry a new unanswered card, and marking after
    it was stored would settle that card instead of the one that was answered. A Deep Research
    clarify resolves through a status event that already carries its own record, so only a resume value is recorded here.
    """
    chat_id = session.request.chat_id
    if not chat_id:
        return
    extra = session.collector.extra_data
    collector_clarification = extra.get("clarification") if isinstance(extra, dict) else None
    collector_clarification_answered = (
        isinstance(collector_clarification, dict) and collector_clarification.get("answered") is True
    )
    resume_value = session.request.resume_value
    if resume_value is None and not collector_clarification_answered:
        return
    record: HitlAnswerRecord | None = {"by": "user", "value": resume_value} if resume_value is not None else None
    await mark_pending_clarification_answered(chat_id, record)
