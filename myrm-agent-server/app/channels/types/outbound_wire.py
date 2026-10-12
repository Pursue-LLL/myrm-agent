"""Typed shape of the JSON wire form of ``OutboundMessage``.

[INPUT]
(No external dependencies, pure type declarations that mirror the dataclasses in ``messages`` and ``components``)

[OUTPUT]
- OutboundWire: the dict ``OutboundMessage.to_dict`` writes and ``OutboundMessage.from_dict`` reads
- MediaWire, ComponentWire, SelectOptionWire, ToolStepWire, QuickReplyWire, CorrelationWire: its nested parts

[POS]
What the durable outbox and held reply drafts persist. ``from_dict`` reads typed keys through these shapes
instead of ``object`` values. Each shape lists exactly the fields of the dataclass it mirrors (plus the
``__type__`` tag ``to_dict`` adds), and a test keeps them in step.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict


class MediaWire(TypedDict):
    __type__: NotRequired[str]
    media_type: str
    url: NotRequired[str | None]
    path: NotRequired[str | None]
    filename: NotRequired[str | None]
    mime_type: NotRequired[str | None]
    caption: NotRequired[str | None]
    ephemeral: NotRequired[bool]


class SelectOptionWire(TypedDict):
    __type__: NotRequired[str]
    label: str
    value: str
    description: NotRequired[str]


class ComponentWire(TypedDict):
    """A button or a select menu; ``__type__`` says which, and the other kind's keys are absent."""

    __type__: str
    action_id: str
    label: NotRequired[str]
    style: NotRequired[str]
    value: NotRequired[str]
    url: NotRequired[str]
    placeholder: NotRequired[str]
    options: NotRequired[list[SelectOptionWire]]


class ToolStepWire(TypedDict):
    __type__: NotRequired[str]
    name: NotRequired[str]
    label: NotRequired[str]
    detail: NotRequired[str | None]


class QuickReplyWire(TypedDict):
    __type__: NotRequired[str]
    label: str
    text: str
    required: NotRequired[bool]


class CorrelationWire(TypedDict):
    __type__: NotRequired[str]
    channel: str
    chat_id: NotRequired[str | None]
    thread_id: NotRequired[str | None]
    user_id: NotRequired[str | None]
    trace_id: NotRequired[str | None]
    locale: NotRequired[str | None]


class OutboundWire(TypedDict):
    __type__: NotRequired[str]
    channel: str
    recipient_id: str
    content: str
    user_id: str
    metadata: NotRequired[dict[str, object] | None]
    media: NotRequired[list[MediaWire]]
    reply_to_id: NotRequired[str | None]
    thread_id: NotRequired[str | None]
    reasoning: NotRequired[str | None]
    tool_steps: NotRequired[list[ToolStepWire]]
    components: NotRequired[list[list[ComponentWire]]]
    quick_replies: NotRequired[list[QuickReplyWire]]
    priority: NotRequired[int]
    correlation_context: NotRequired[CorrelationWire | None]
