"""WhatsApp inbound message keys — what a reaction must quote back.

[INPUT]
- The bridge's message event (``from`` / ``id`` / ``fromMe`` / ``participant``), as received

[OUTPUT]
- inbound_message_key: the Baileys key (``remoteJid`` / ``id`` / ``fromMe`` / optional ``participant``) of one inbound event
- MessageKeys: bounded (chat, message id) → key memory the channel fills on inbound and reads on react

[POS]
WhatsApp reactions must target a message by its full Baileys key. The host knows only the message id and the
normalised chat id, which is not the raw ``remoteJid`` for a LID chat and carries no ``participant`` for a group
message, so the key as received is kept for the reaction to pass back unchanged.
"""

from __future__ import annotations

from collections import OrderedDict

_MAX_KEYS = 1024


def inbound_message_key(event: dict[str, object], remote_jid: str) -> dict[str, object] | None:
    """The key Baileys gave an inbound message, or None when the event carries no id."""
    message_id = event.get("id")
    if not message_id:
        return None
    key: dict[str, object] = {"remoteJid": remote_jid, "id": str(message_id), "fromMe": event.get("fromMe") is True}
    participant = event.get("participant")
    if isinstance(participant, str) and participant:
        key["participant"] = participant
    return key


class MessageKeys:
    """Bounded memory of inbound message keys; the oldest entry is dropped when full.

    A reaction lands within seconds of its message, so a short memory covers it; a miss makes the bridge fall back
    to the key it can rebuild itself.
    """

    def __init__(self, max_keys: int = _MAX_KEYS) -> None:
        self._max_keys = max_keys
        self._keys: OrderedDict[tuple[str, str], dict[str, object]] = OrderedDict()

    def note(self, chat_id: str, message_id: str, key: dict[str, object]) -> None:
        self._keys[(chat_id, message_id)] = key
        self._keys.move_to_end((chat_id, message_id))
        while len(self._keys) > self._max_keys:
            self._keys.popitem(last=False)

    def get(self, chat_id: str, message_id: str) -> dict[str, object] | None:
        return self._keys.get((chat_id, message_id))
