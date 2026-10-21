"""The provider wait is worded once, in the diagnostic message, never re-appended by the channel reply."""

from __future__ import annotations

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic
from myrm_agent_harness.toolkits.llms.errors import FailoverReason, MyrmLLMError

from app.channels.types import InboundMessage
from app.core.channel_bridge.agent_executor.execute_errors import build_llm_error_reply


def _inbound_message() -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="chat-1",
        user_id="user-1",
        is_group=False,
        mentioned=False,
        metadata={"locale": "en"},
    )


def test_llm_error_reply_states_the_wait_exactly_once() -> None:
    diagnostic = LLMErrorDiagnostic.diagnose(Exception("rate limit"), locale="en", cooldown_remaining_ms=3 * 3_600_000)
    exc = MyrmLLMError(
        error_code=FailoverReason.RATE_LIMIT,
        default_msg="rate limited",
        context={"cooldown_remaining_ms": 3 * 3_600_000},
        diagnostic_result={
            "user_message": diagnostic.user_message,
            "resolution_steps": list(diagnostic.resolution_steps),
        },
    )

    reply = build_llm_error_reply(_inbound_message(), exc)

    assert reply.content.count("3 hours") == 1
    assert "retry in" not in reply.content.lower()
