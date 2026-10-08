"""A skill-bound slash command reaches the agent as ``[use skill] ...``; channel context must not bury it.

The harness recognizes an explicit skill invocation only at the very start of the user's text, so reply
context, group context and the delivery banner all belong behind the tag.
"""

from __future__ import annotations

from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag

from app.channels.types import ContextEntry, InboundMessage, ReplyContext
from app.core.channel_bridge.agent_executor.helpers import build_channel_inbound_query


def _message(
    content: str,
    *,
    reply_to: ReplyContext | None = None,
    context: tuple[ContextEntry, ...] = (),
) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="u1",
        content=content,
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="c1",
        user_id="u1",
        is_group=bool(context),
        mentioned=True,
        context_messages=context,
        metadata={},
        reply_to=reply_to,
    )


def test_skill_command_stays_first_behind_banner_reply_and_group_context() -> None:
    reply = ReplyContext(message_id="m1", content="meeting cancelled", sender_name="Manager")
    context = (ContextEntry(sender_id="coworker", content="got it", timestamp=1.0),)

    out = build_channel_inbound_query(_message("[use daily-report] update my calendar", reply_to=reply, context=context))

    assert isinstance(out, str)
    invocation = parse_use_tag(out)
    assert invocation is not None
    assert invocation.references == ("daily-report",)
    text = invocation.text
    assert text.startswith("[Inbound channel message] channel=telegram")
    assert text.index("[Recent group chat messages for context]") < text.index("[Replying to Manager]")
    assert text.endswith("update my calendar")


def test_plain_message_is_unchanged_by_the_skill_tag_handling() -> None:
    out = build_channel_inbound_query(_message("just chatting"))
    assert isinstance(out, str)
    assert out.startswith("[Inbound channel message] channel=telegram")
    assert out.endswith("just chatting")
    assert parse_use_tag(out) is None
