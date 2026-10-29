"""InboundMessage wire format: every persisted field survives a JSON round trip.

The inbound journal stores ``inbound_to_wire(msg)`` and replays ``inbound_from_wire`` after a restart; a field the
wire form drops is a field the replayed turn runs without.
"""

from __future__ import annotations

import dataclasses
import json
from typing import TYPE_CHECKING, get_type_hints

import pytest

from app.channels.types import ChannelCapabilities, ContextEntry, InboundMessage, ReplyContext
from app.channels.types.inbound_wire import (
    ContextEntryWire,
    InboundWire,
    ReplyContextWire,
    inbound_from_wire,
    inbound_to_wire,
)
from tests.channels.inbound_message_testkit import full_message

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

# Derived from the session at replay time, so the wire form leaves it out.
_NOT_PERSISTED = {"channel_capabilities"}
_REQUIRED = {"channel", "sender_id", "content"}


def _default_of(field: dataclasses.Field[object]) -> object:
    if field.default is not dataclasses.MISSING:
        return field.default
    assert field.default_factory is not dataclasses.MISSING
    return field.default_factory()


def _through_json(msg: InboundMessage) -> InboundMessage:
    return inbound_from_wire(json.loads(json.dumps(inbound_to_wire(msg))))


def test_the_fixture_sets_every_persisted_field_to_a_non_default_value() -> None:
    msg = full_message()
    for field in dataclasses.fields(InboundMessage):
        if field.name in _NOT_PERSISTED | _REQUIRED:
            continue
        default = _default_of(field)
        assert getattr(msg, field.name) != default, f"{field.name} still has its default value"


def test_every_persisted_field_survives_a_json_round_trip() -> None:
    original = full_message()

    assert _through_json(original) == original


def test_channel_capabilities_is_not_persisted() -> None:
    original = dataclasses.replace(full_message(), channel_capabilities=ChannelCapabilities())

    assert _through_json(original).channel_capabilities is None


def test_a_minimal_message_round_trips() -> None:
    original = InboundMessage(channel="c", sender_id="s", content="x", sent_at=1.0)

    assert _through_json(original) == original


_SHAPES = [
    pytest.param(InboundWire, InboundMessage, _NOT_PERSISTED, id="inbound"),
    pytest.param(ContextEntryWire, ContextEntry, set(), id="context_entry"),
    pytest.param(ReplyContextWire, ReplyContext, set(), id="reply_context"),
]


@pytest.mark.parametrize(("shape", "dataclass_type", "left_out"), _SHAPES)
def test_wire_keys_match_the_dataclass_fields(shape: type, dataclass_type: type[DataclassInstance], left_out: set[str]) -> None:
    fields = {field.name for field in dataclasses.fields(dataclass_type)} - left_out

    assert set(get_type_hints(shape)) == fields
