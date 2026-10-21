"""OutboundMessage wire format: every nested dataclass is type-tagged and survives a JSON round trip.

The durable outbox and the dead-letter queue persist ``OutboundMessage.to_dict()`` and rebuild it with
``from_dict()``; a message that cannot be rebuilt can never be delivered.
"""

from __future__ import annotations

import json

import pytest

from app.channels.types import (
    ActionButton,
    ButtonStyle,
    CorrelationContext,
    MediaAttachment,
    MediaType,
    MessagePriority,
    OutboundMessage,
    QuickReply,
    SelectMenu,
    SelectOption,
    ToolStep,
)

_HANDOFF_BUTTON = ActionButton(
    label="Continue in browser",
    action_id="web:continue_chat",
    style=ButtonStyle.DEFAULT,
    url="https://example.test/chat/abc",
)
_APPROVE_BUTTON = ActionButton(label="Approve", action_id="approval:approve:req-1", style=ButtonStyle.PRIMARY, value="req-1")
_MODEL_MENU = SelectMenu(
    action_id="model:pick",
    placeholder="Pick a model",
    options=(
        SelectOption(label="Fast", value="fast", description="Low latency"),
        SelectOption(label="Deep", value="deep"),
    ),
)


def _message(**overrides: object) -> OutboundMessage:
    fields: dict[str, object] = {"channel": "feishu", "recipient_id": "user_1", "content": "hello", "user_id": "u1"}
    fields.update(overrides)
    return OutboundMessage(**fields)  # type: ignore[arg-type]


def _through_json(msg: OutboundMessage) -> OutboundMessage:
    """Persist/reload exactly like the delivery store does (JSON on disk)."""
    return OutboundMessage.from_dict(json.loads(json.dumps(msg.to_dict())))


def test_full_message_round_trips_through_json() -> None:
    original = _message(
        metadata={"locale": "zh", "retries": 2, "flags": {"silent": False}},
        media=(
            MediaAttachment(
                media_type=MediaType.IMAGE,
                path="/tmp/shot.png",
                filename="shot.png",
                mime_type="image/png",
                caption="screen",
                ephemeral=True,
            ),
            MediaAttachment(media_type=MediaType.DOCUMENT, url="https://example.test/report.pdf"),
        ),
        reply_to_id="m-9",
        thread_id="t-1",
        reasoning="thinking",
        tool_steps=(ToolStep(name="search", label="Searching", detail="query"), ToolStep(name="read", label="Reading")),
        components=((_APPROVE_BUTTON, _MODEL_MENU), (_HANDOFF_BUTTON,)),
        quick_replies=(QuickReply(label="Yes", text="yes", required=True), QuickReply(label="No", text="no")),
        priority=MessagePriority.SYSTEM,
        correlation_context=CorrelationContext(channel="feishu", chat_id="c1", thread_id="t-1", user_id="u1", locale="zh"),
    )

    assert _through_json(original) == original


@pytest.mark.parametrize(
    "component",
    [
        pytest.param(_HANDOFF_BUTTON, id="url-button"),
        pytest.param(_APPROVE_BUTTON, id="callback-button"),
        pytest.param(ActionButton(label="Delete", action_id="x:del", style=ButtonStyle.DANGER), id="danger-button"),
        pytest.param(_MODEL_MENU, id="select-menu"),
        pytest.param(SelectMenu(action_id="empty:pick", placeholder="", options=()), id="empty-select-menu"),
    ],
)
def test_every_component_type_round_trips(component: ActionButton | SelectMenu) -> None:
    original = _message(components=((component,),))

    assert _through_json(original) == original


def test_web_handoff_button_message_is_recoverable() -> None:
    """Every IM reply carries this button when a public ingress URL exists - it must never poison the outbox."""
    original = _message(components=((_HANDOFF_BUTTON,),))

    restored = _through_json(original)

    assert restored.components == ((_HANDOFF_BUTTON,),)


def test_nested_dataclasses_carry_their_type_tag() -> None:
    wire = _message(
        components=((_APPROVE_BUTTON, _MODEL_MENU),), media=(MediaAttachment(media_type=MediaType.IMAGE, path="/tmp/a.png"),)
    ).to_dict()

    button, menu = wire["components"][0]  # type: ignore[index]
    assert wire["__type__"] == "OutboundMessage"
    assert button["__type__"] == "ActionButton"
    assert menu["__type__"] == "SelectMenu"
    assert menu["options"][0]["__type__"] == "SelectOption"
    assert wire["media"][0]["__type__"] == "MediaAttachment"  # type: ignore[index]
