"""Hand a finished turn's unread steering instructions back to the client.

[INPUT]
- app.schemas.streaming::SSEEnvelope (POS: 业务层 SSE 序列化防腐层)
- app.services.agent.stream_session.stream_session_types::AgentStreamSession (POS: 单轮会话状态，stream_session 各模块共同传递的对象)
- myrm_agent_harness.utils.runtime.steering::SteeringToken (POS: Steering token mechanism. Allows external message injection during Agent runtime to interrupt the current tool chain)

[OUTPUT]
- STEERING_UNREAD_EVENT: the `type` of the SSE event that carries the unread instructions
- unread_steering_chunk: close the turn's steering token and return what it accepted but the model never read

[POS]
End of the steering contract for web turns. A turn that completed normally read everything it accepted before its last
gate; one that ended by itself in any other way (fatal error, iteration limit without a goal, provider-window hold)
still holds instructions the model never saw. The turn's owner closes the token here and sends them back to the client
in a single event, which puts them in its follow-up queue, so an accepted instruction is read or returned, never
dropped. A cancelled turn (Stop, disconnect, E-Stop) is the one exception: cancelling ends the run and the guidance
addressed to it, so nothing is sent.
"""

from __future__ import annotations

import logging

from app.schemas.streaming import SSEEnvelope
from app.services.agent.stream_session.stream_session_types import AgentStreamSession

logger = logging.getLogger(__name__)

STEERING_UNREAD_EVENT = "steering_unread"


def unread_steering_chunk(session: AgentStreamSession) -> str | None:
    """Close the session's steering token and return its unread instructions as one SSE chunk.

    Returns None when the turn has no token, read everything it accepted, or was cancelled. After the call the token
    refuses every later steer/redirect, so an instruction arriving now is refused over HTTP and stays with its sender.
    """
    token = session.steering_token
    if token is None:
        return None
    unread = token.close_and_drain()
    if not unread:
        return None
    if session.cancel_token.is_cancelled:
        logger.info(
            "Cancelled turn ends with %d unread steering instruction(s): chat_id=%s", len(unread), session.request.chat_id
        )
        return None
    logger.warning(
        "Turn ended with %d steering instruction(s) the model never read; handing them back: chat_id=%s",
        len(unread),
        session.request.chat_id,
    )
    event: dict[str, object] = {
        "type": STEERING_UNREAD_EVENT,
        "messageId": session.params.message_id,
        "data": {"count": len(unread), "messages": unread},
    }
    return SSEEnvelope.from_any(event).to_sse_chunk()
