"""A stand-in VoiceClient for the receiver tests: the bot's SSRC, and the given key, mode and DAVE session."""

from __future__ import annotations

from unittest.mock import MagicMock


def make_mock_vc(mode: str = "", dave_session: object | None = None, *, key: bytes = bytes(32)) -> MagicMock:
    vc = MagicMock()
    conn = MagicMock()
    conn.secret_key = list(key)
    conn.ssrc = 999
    conn.hook = None
    conn.mode = mode
    conn.dave_session = dave_session
    vc._connection = conn
    vc.channel = MagicMock()
    vc.channel.members = []
    vc.user = MagicMock()
    vc.user.id = 1
    vc.mode = mode
    return vc
