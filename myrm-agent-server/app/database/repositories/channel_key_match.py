"""Boundary-safe matches of a channel conversation in ``Chat.channel_session_key``.

[INPUT]
- database.models.chat::Chat (POS: ``channel_session_key`` column)

[OUTPUT]
- channel_key_extends(): the conversation's key and every key that continues it after a ``:``
- channel_key_epochs(): the conversation's key and its reset-epoch keys (``:e=<epoch>``)

[POS]
A channel session key is ``{channel}:{peer_kind}:{peer}[:thread:..][:agent:..]`` with an optional ``:e=<epoch>``
suffix, and a peer id keeps ``_`` and ``-`` when it is sanitised. A ``LIKE`` prefix therefore also matches another peer
(``u1`` and ``u10``), treats ``_`` as a wildcard and scans the table. These matches compare against the key at its
segment boundary with an index range instead: ``:`` (0x3A) is followed by ``;`` (0x3B) and ``=`` (0x3D) by ``>`` (0x3E).
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, or_

from app.database.models.chat import Chat


def channel_key_extends(base_key: str) -> ColumnElement[bool]:
    """Match ``base_key`` and every key that continues it with another segment (topic, agent or epoch)."""
    key = Chat.channel_session_key
    return or_(key == base_key, (key >= f"{base_key}:") & (key < f"{base_key};"))


def channel_key_epochs(base_key: str) -> ColumnElement[bool]:
    """Match ``base_key`` and its reset-epoch keys, not the keys of a topic or an agent of the same peer."""
    key = Chat.channel_session_key
    return or_(key == base_key, (key >= f"{base_key}:e=") & (key < f"{base_key}:e>"))
