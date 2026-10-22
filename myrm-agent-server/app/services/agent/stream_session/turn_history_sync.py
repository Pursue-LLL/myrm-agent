"""Turn history sync — declare how a turn's agent thread relates to the stored chat, and record it once the turn completed.

[INPUT]
- app.services.chat.history_sync (POS: digest comparison and commit of the thread-mirrors-chat record)
- app.services.agent.params::AgentRequest (POS: chat, resume and regenerate flags of the request)
- app.services.agent.stream_session.stream_session_types::AgentStreamSession (POS: outcome of the turn)

[OUTPUT]
- resolve_turn_history_mode: the ``history_mode`` a turn declares to the agent loop, or ``None`` when it declares none
- commit_turn_history_sync: record that the thread mirrors the stored chat after a turn that completed on it

[POS]
Stream-layer policy of the single-authority history rule (mechanics live in ``services/chat/history_sync``).
A turn continues the agent thread only when the thread provably mirrors the stored chat: the thread is what
the model saw (tool traces included), the stored chat is what the user saw. Anything else rebuilds the thread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.runtime.context.session import HistoryMode

from app.services.chat.history_sync import commit_history_sync, decide_history_mode

if TYPE_CHECKING:
    from app.services.agent.params import AgentRequest
    from app.services.agent.stream_session.stream_session_types import AgentStreamSession

# The agent loop reports the mode it ran a turn with. Only these mean the turn ran on the chat's thread: a
# turn served by another lane (fast, research, workflow) leaves the thread without the exchange.
_THREAD_BOUND_MODES = frozenset({"continue", "replace", "resume"})


async def resolve_turn_history_mode(request: AgentRequest, *, exclude_message_id: str | None) -> HistoryMode | None:
    """Declare how the turn relates to the agent thread.

    A resume continues the thread it paused on and a turn without a chat has none, so neither declares a mode.
    A regenerate always rebuilds: the thread still holds the answer that is being replaced.
    """
    if request.resume_value is not None or not request.chat_id:
        return None
    if request.sibling_group_id is not None:
        return "replace"
    return await decide_history_mode(request.chat_id, exclude_message_id=exclude_message_id)


async def commit_turn_history_sync(session: AgentStreamSession, *, pending_hitl: bool) -> None:
    """Record that the thread mirrors the stored chat, when the turn completed on the thread.

    A turn that was cancelled, failed, is waiting on the user, or ran on another lane records nothing: the
    previous record no longer matches the stored chat, so the next turn rebuilds the thread.
    """
    request = session.request
    if not request.chat_id or not request.message_id:
        return
    if pending_hitl or session.had_fatal_error or session.cancel_token.is_cancelled:
        return
    if _reported_history_mode(session) not in _THREAD_BOUND_MODES:
        return
    await commit_history_sync(request.chat_id, request.message_id)


def _reported_history_mode(session: AgentStreamSession) -> object:
    extra_data = session.collector.extra_data or {}
    economics = extra_data.get("tokenEconomics")
    turn_context = economics.get("turn_context") if isinstance(economics, dict) else None
    return turn_context.get("history_mode") if isinstance(turn_context, dict) else None
