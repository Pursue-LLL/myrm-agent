"""Auto-topic only acts on a message that names the chat it came from."""

from __future__ import annotations

import pytest

from app.channels.types import InboundMessage
from tests.channels.providers.telegram.telegram_channel_factories import make_topic_channel


@pytest.mark.parametrize("thread_id", [None, "7"], ids=["no_topic_yet", "inside_a_topic"])
@pytest.mark.asyncio
async def test_a_forum_message_without_a_chat_id_is_passed_through_untouched(thread_id: str | None) -> None:
    channel, client = make_topic_channel(auto_topic=True)
    msg = InboundMessage(
        channel="telegram",
        sender_id="42",
        sender_name="Alice",
        content="hello",
        chat_id=None,
        is_group=True,
        thread_id=thread_id,
        metadata={"is_forum": True},
    )

    result = await channel._pre_emit_hook(msg)

    assert result is msg
    client.create_forum_topic.assert_not_called()
    client.edit_forum_topic.assert_not_called()
    assert not channel._background_tasks
