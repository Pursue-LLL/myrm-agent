"""Two topics of one group, each bound to a different agent, must not share router state.

The router keeps its running-task, /stop, YOLO and approval state in string-keyed maps. Before
the topic dimension entered those keys, answering in one topic overwrote the other's running
task, so `/stop` in the first topic cancelled the second topic's turn.
"""

from __future__ import annotations

from app.channels.routing.router_keys import routing_state_key
from app.channels.routing.session_gate import gate_key
from app.channels.types import InboundMessage

_GROUP_CHAT = "-1001234"


def _group_message(thread_id: str) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id="user-1",
        content="hi",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id=_GROUP_CHAT,
        user_id="user-1",
        is_group=True,
        mentioned=True,
        thread_id=thread_id,
        metadata={"locale": "en"},
    )


def test_two_topics_do_not_overwrite_each_others_active_task() -> None:
    sales_key = routing_state_key("telegram", _GROUP_CHAT, "100")
    support_key = routing_state_key("telegram", _GROUP_CHAT, "200")

    active_tasks: dict[str, str] = {}
    active_tasks[sales_key] = "sales-turn"
    active_tasks[support_key] = "support-turn"

    assert active_tasks[sales_key] == "sales-turn", "the second topic must not overwrite the first"
    assert active_tasks[support_key] == "support-turn"


def test_stop_in_one_topic_cancels_that_topics_turn() -> None:
    sales_key = routing_state_key("telegram", _GROUP_CHAT, "100")
    support_key = routing_state_key("telegram", _GROUP_CHAT, "200")

    active_tasks = {sales_key: "sales-turn", support_key: "support-turn"}
    cancelled = active_tasks.pop(sales_key, None)

    assert cancelled == "sales-turn"
    assert active_tasks == {support_key: "support-turn"}


def test_debounce_queue_is_per_topic() -> None:
    assert gate_key(_group_message("100")) != gate_key(_group_message("200"))


def test_debounce_queue_unchanged_for_dm() -> None:
    dm = InboundMessage(
        channel="telegram",
        sender_id="user-9",
        content="hi",
        sent_at=1.0,
        sent_timezone="UTC",
        chat_id="user-9",
        user_id="user-9",
        is_group=False,
        mentioned=False,
        metadata={"locale": "en"},
    )
    assert gate_key(dm) == "telegram:user-9"
