"""WhatsApp reactions quote the Baileys key of the inbound message they react to.

The channel remembers the key each inbound event carried; a reaction passes it to the bridge unchanged so a group
message keeps its ``participant`` and a LID chat keeps its raw ``remoteJid``. A message the channel never saw is
addressed by chat and id alone, as before.
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.whatsapp.channel import WhatsAppChannel
from app.channels.providers.whatsapp.helpers import _BRIDGE_SCRIPT
from app.channels.providers.whatsapp.message_keys import MessageKeys, inbound_message_key

GROUP = "120363001122@g.us"
SENDER_LID = "9988776655@lid"
SENDER_PN = "8615546316576@s.whatsapp.net"


def _channel() -> tuple[WhatsAppChannel, list[dict[str, object]]]:
    ch = WhatsAppChannel(auth_dir="/tmp/test_wa_reaction_key")
    ch._self_jid = "8610000000000:5@s.whatsapp.net"
    ch._connected.set()
    ch._process = MagicMock()
    ch._process.stdin = MagicMock()
    ch._process.stdin.drain = AsyncMock()
    ch._emit_inbound = AsyncMock()  # type: ignore[method-assign]
    sent: list[dict[str, object]] = []
    ch._process.stdin.write = lambda data: sent.append(json.loads(data.decode()))
    return ch, sent


async def _receive(ch: WhatsAppChannel, **fields: object) -> str:
    """Feed one bridge message event and return the chat id the channel emitted it under."""
    event = {"type": "message", "text": "hi", "fromMe": False, "isGroup": False, **fields}
    await ch._handle_bridge_event(json.dumps(event))
    return str(ch._emit_inbound.await_args.args[0].chat_id)


class TestReactionKey:
    @pytest.mark.asyncio
    async def test_direct_chat_reaction_quotes_the_received_key(self) -> None:
        ch, sent = _channel()
        chat = await _receive(ch, **{"from": SENDER_PN, "id": "M1"})

        await ch.react_to_message(chat, "M1", "\U0001f440")

        assert sent == [
            {
                "type": "react",
                "to": SENDER_PN,
                "messageId": "M1",
                "emoji": "\U0001f440",
                "key": {"remoteJid": SENDER_PN, "id": "M1", "fromMe": False},
            }
        ]

    @pytest.mark.asyncio
    async def test_group_reaction_names_the_message_author(self) -> None:
        ch, sent = _channel()
        chat = await _receive(ch, **{"from": GROUP, "id": "G1", "participant": SENDER_LID, "isGroup": True})

        await ch.react_to_message(chat, "G1", "\U0001f440")

        assert sent[0]["key"] == {"remoteJid": GROUP, "id": "G1", "fromMe": False, "participant": SENDER_LID}

    @pytest.mark.asyncio
    async def test_lid_chat_keeps_its_raw_jid_while_the_chat_id_is_the_phone_number(self) -> None:
        ch, sent = _channel()
        chat = await _receive(ch, **{"from": SENDER_LID, "fromAlt": SENDER_PN, "id": "L1"})

        await ch.react_to_message(chat, "L1", "\U0001f440")

        assert chat == SENDER_PN
        assert sent[0]["to"] == SENDER_PN
        assert sent[0]["key"] == {"remoteJid": SENDER_LID, "id": "L1", "fromMe": False}

    @pytest.mark.asyncio
    async def test_self_chat_message_is_marked_from_me(self) -> None:
        ch, sent = _channel()
        own = "8610000000000@s.whatsapp.net"
        chat = await _receive(ch, **{"from": own, "id": "S1", "fromMe": True})

        await ch.react_to_message(chat, "S1", "\U0001f440")

        assert sent[0]["key"] == {"remoteJid": own, "id": "S1", "fromMe": True}

    @pytest.mark.asyncio
    async def test_removing_a_reaction_quotes_the_same_key(self) -> None:
        ch, sent = _channel()
        chat = await _receive(ch, **{"from": GROUP, "id": "G1", "participant": SENDER_PN, "isGroup": True})

        await ch.react_to_message(chat, "G1", "")

        assert sent[0]["emoji"] == ""
        assert sent[0]["key"] == {"remoteJid": GROUP, "id": "G1", "fromMe": False, "participant": SENDER_PN}

    @pytest.mark.asyncio
    async def test_unseen_message_is_addressed_by_chat_and_id_alone(self) -> None:
        ch, sent = _channel()

        await ch.react_to_message(SENDER_PN, "UNSEEN", "\U0001f440")

        assert sent == [{"type": "react", "to": SENDER_PN, "messageId": "UNSEEN", "emoji": "\U0001f440"}]

    @pytest.mark.asyncio
    async def test_same_message_id_in_another_chat_does_not_borrow_the_key(self) -> None:
        ch, sent = _channel()
        await _receive(ch, **{"from": GROUP, "id": "DUP", "participant": SENDER_PN, "isGroup": True})

        await ch.react_to_message(SENDER_PN, "DUP", "\U0001f440")

        assert "key" not in sent[0]


class TestMessageKeys:
    def test_event_without_an_id_has_no_key(self) -> None:
        assert inbound_message_key({"from": SENDER_PN}, SENDER_PN) is None

    def test_oldest_key_is_dropped_when_full(self) -> None:
        keys = MessageKeys(max_keys=2)
        for n in range(3):
            keys.note("c", f"m{n}", {"id": f"m{n}"})

        assert keys.get("c", "m0") is None
        assert keys.get("c", "m1") == {"id": "m1"}
        assert keys.get("c", "m2") == {"id": "m2"}

    def test_noting_a_message_again_keeps_it_fresh(self) -> None:
        keys = MessageKeys(max_keys=2)
        keys.note("c", "m0", {"id": "m0"})
        keys.note("c", "m1", {"id": "m1"})
        keys.note("c", "m0", {"id": "m0"})
        keys.note("c", "m2", {"id": "m2"})

        assert keys.get("c", "m1") is None
        assert keys.get("c", "m0") == {"id": "m0"}


def test_bridge_quotes_the_key_the_host_sends() -> None:
    """The bridge has no runtime test harness; this guards the half of the contract that lives in its source."""
    source = _BRIDGE_SCRIPT.read_text(encoding="utf-8")
    react_branch = re.search(r'cmd\.type === "react".*?\n    }\n', source, re.DOTALL)

    assert react_branch is not None
    assert "key: cmd.key || { remoteJid: jid, id: cmd.messageId }" in react_branch.group(0)
