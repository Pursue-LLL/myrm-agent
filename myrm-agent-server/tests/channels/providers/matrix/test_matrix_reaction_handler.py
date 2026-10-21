"""Unit tests for the Matrix ``m.reaction`` annotation event handler.

Validates that ``handle_reaction`` (1) translates Matrix annotation keys to
the canonical Unicode emoji vocabulary consumed by ``parse_approval_command``,
(2) preserves target message lineage via ``target_message_id`` metadata,
(3) drops events that lack the required relation/key fields, and (4) ignores
self-reactions to keep the bot from reviving its own approval gate.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.channels.providers.matrix.handlers import handle_reaction
from app.channels.types import InboundMessage


def _reaction_event(
    *,
    sender: str = "@alice:matrix.org",
    room_id: str = "!room:matrix.org",
    event_id: str = "$reaction-1",
    target_event_id: str = "$target-msg",
    rel_type: str = "m.annotation",
    key: str = "👍",
) -> SimpleNamespace:
    relates_to: SimpleNamespace | None
    if target_event_id or rel_type or key:
        relates_to = SimpleNamespace(
            rel_type=rel_type,
            event_id=target_event_id,
            key=key,
        )
    else:
        relates_to = None
    return SimpleNamespace(
        sender=sender,
        room_id=room_id,
        event_id=event_id,
        content=SimpleNamespace(relates_to=relates_to),
    )


async def _capture(event: SimpleNamespace, **kwargs: Any) -> list[InboundMessage]:
    received: list[InboundMessage] = []

    async def emit(msg: InboundMessage) -> None:
        received.append(msg)

    defaults: dict[str, Any] = {
        "user_id": "@bot:matrix.org",
        "dm_rooms": {},
        "emit_inbound_fn": emit,
    }
    defaults.update(kwargs)
    await handle_reaction(event, **defaults)
    return received


class TestMatrixReactionHandler:
    @pytest.mark.asyncio
    async def test_known_emoji_passes_through(self) -> None:
        received = await _capture(_reaction_event(key="👍"))
        assert len(received) == 1
        assert received[0].content == "\U0001f44d"
        assert received[0].channel == "matrix"
        assert received[0].sender_id == "@alice:matrix.org"
        assert received[0].metadata["reaction"] is True
        assert received[0].metadata["target_message_id"] == "$target-msg"
        assert received[0].message_id == "$target-msg"
        assert received[0].is_group is True

    @pytest.mark.asyncio
    async def test_plus_one_alias_maps_to_thumbsup(self) -> None:
        received = await _capture(_reaction_event(key="+1"))
        assert len(received) == 1
        assert received[0].content == "\U0001f44d"

    @pytest.mark.asyncio
    async def test_infinity_with_variation_selector(self) -> None:
        received = await _capture(_reaction_event(key="\u267e\ufe0f"))
        assert len(received) == 1
        assert received[0].content == "\u267e"

    @pytest.mark.asyncio
    async def test_thumbsdown_maps_to_deny(self) -> None:
        received = await _capture(_reaction_event(key="-1"))
        assert len(received) == 1
        assert received[0].content == "\U0001f44e"

    @pytest.mark.asyncio
    async def test_unknown_key_passes_through_unchanged(self) -> None:
        """Unknown keys forward as-is so ``parse_approval_command`` can decide."""
        received = await _capture(_reaction_event(key="🎉"))
        assert len(received) == 1
        assert received[0].content == "🎉"

    @pytest.mark.asyncio
    async def test_dm_room_marks_not_group(self) -> None:
        event = _reaction_event(room_id="!dm:matrix.org")
        received = await _capture(event, dm_rooms={"!dm:matrix.org": True})
        assert len(received) == 1
        assert received[0].is_group is False

    @pytest.mark.asyncio
    async def test_self_reaction_filtered(self) -> None:
        received = await _capture(_reaction_event(sender="@bot:matrix.org"))
        assert received == []

    @pytest.mark.asyncio
    async def test_missing_relates_to_dropped(self) -> None:
        event = SimpleNamespace(
            sender="@alice:matrix.org",
            room_id="!room:matrix.org",
            event_id="$r1",
            content=SimpleNamespace(relates_to=None),
        )
        received = await _capture(event)
        assert received == []

    @pytest.mark.asyncio
    async def test_non_annotation_relation_dropped(self) -> None:
        received = await _capture(
            _reaction_event(rel_type="m.replace"),
        )
        assert received == []

    @pytest.mark.asyncio
    async def test_empty_key_dropped(self) -> None:
        received = await _capture(_reaction_event(key=""))
        assert received == []

    @pytest.mark.asyncio
    async def test_missing_target_event_id_dropped(self) -> None:
        received = await _capture(_reaction_event(target_event_id=""))
        assert received == []
