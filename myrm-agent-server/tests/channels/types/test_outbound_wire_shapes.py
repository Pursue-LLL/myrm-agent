"""Wire-shape declarations list exactly the fields of the dataclasses they mirror.

``OutboundMessage.from_dict`` reads persisted records through the TypedDicts in ``outbound_wire``. A dataclass
field added without its wire key would still be written by ``to_dict`` but stay invisible to the type checker
on the way back in, so the key sets are held equal here.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, get_type_hints

import pytest

from app.channels.types import (
    ActionButton,
    CorrelationContext,
    MediaAttachment,
    OutboundMessage,
    QuickReply,
    SelectMenu,
    SelectOption,
    ToolStep,
)
from app.channels.types.outbound_wire import (
    ComponentWire,
    CorrelationWire,
    MediaWire,
    OutboundWire,
    QuickReplyWire,
    SelectOptionWire,
    ToolStepWire,
)

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

_TYPE_TAG = "__type__"

_SHAPES = [
    pytest.param(OutboundWire, (OutboundMessage,), id="outbound"),
    pytest.param(MediaWire, (MediaAttachment,), id="media"),
    pytest.param(SelectOptionWire, (SelectOption,), id="select_option"),
    pytest.param(ToolStepWire, (ToolStep,), id="tool_step"),
    pytest.param(QuickReplyWire, (QuickReply,), id="quick_reply"),
    pytest.param(CorrelationWire, (CorrelationContext,), id="correlation"),
    pytest.param(ComponentWire, (ActionButton, SelectMenu), id="component_button_and_menu"),
]


@pytest.mark.parametrize(("shape", "dataclass_types"), _SHAPES)
def test_wire_keys_match_the_dataclass_fields(shape: type, dataclass_types: tuple[type[DataclassInstance], ...]) -> None:
    fields = {field.name for cls in dataclass_types for field in dataclasses.fields(cls)}

    assert set(get_type_hints(shape)) - {_TYPE_TAG} == fields
