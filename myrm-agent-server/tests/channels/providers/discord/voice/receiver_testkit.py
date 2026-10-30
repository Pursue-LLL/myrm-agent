"""A stand-in VoiceClient for the receiver tests: a zero key, the bot's SSRC, and the given mode and DAVE session."""

from __future__ import annotations

from unittest.mock import MagicMock


def make_mock_vc(mode: str = "", dave_session: object | None = None) -> MagicMock:
    vc = MagicMock()
    conn = MagicMock()
    conn.secret_key = [0] * 32
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
