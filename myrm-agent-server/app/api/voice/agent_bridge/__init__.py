"""Server-side voice agent bridge.

[INPUT]
- .bridge (POS: VoiceAgentBridge)

[OUTPUT]
- VoiceAgentBridge

[POS]
Aggregate exit of the voice agent bridge package.
"""

from __future__ import annotations

from .bridge import VoiceAgentBridge
from .common import _MAX_TRANSCRIPT_HISTORY, _SPEECH_INTERRUPTED_NOTE
from .params import _ensure_model_rebuild
from .streams import _extract_speakable_segments
from .turn import _log_turn_latency

__all__ = [
    "VoiceAgentBridge",
    "_ensure_model_rebuild",
    "_extract_speakable_segments",
    "_log_turn_latency",
    "_MAX_TRANSCRIPT_HISTORY",
    "_SPEECH_INTERRUPTED_NOTE",
]
