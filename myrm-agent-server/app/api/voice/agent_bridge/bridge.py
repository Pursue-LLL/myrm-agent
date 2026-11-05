"""[INPUT]
- .turn / .streams / .params / .tts (POS: the four mixins)

[OUTPUT]
- VoiceAgentBridge

[POS]
The voice agent bridge: a dataclass holding the session state, composed with the turn, stream, params and TTS mixins.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

if TYPE_CHECKING:
    from fastapi import WebSocket

    from app.channels.types import VoiceConfig

from .common import _TranscriptEntry
from .params import ParamsMixin
from .streams import StreamMixin
from .tts import TtsMixin
from .turn import TurnMixin


@dataclass
class VoiceAgentBridge(TurnMixin, StreamMixin, ParamsMixin, TtsMixin):
    """Server-side Agent execution bridge for voice sessions."""

    _ws: WebSocket

    _voice_config: VoiceConfig

    _agent_id: str | None

    _chat_id: str | None

    _ws_send_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    _closed: bool = False

    _cancel_token: CancellationToken | None = field(default=None, repr=False)

    _current_turn: str | None = field(default=None, repr=False)

    _transcript: list[_TranscriptEntry] = field(default_factory=list, repr=False)

    _tts_cancel_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    _speech_interrupted_at: float | None = field(default=None, repr=False)

    _stop_spoken_turn: str | None = field(default=None, repr=False)
