"""[INPUT]
- fastapi::WebSocket (POS: voice websocket)

[OUTPUT]
- _TranscriptEntry, logger and the voice-bridge constants

[POS]
Shared primitives of the voice agent bridge.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class _TranscriptEntry:
    role: str
    text: str


logger = logging.getLogger(__name__)


_SENTENCE_END = re.compile(r"[.!?。！？\n]")

_MAX_TRANSCRIPT_HISTORY = 12

_VOICE_SUPERVISOR_TIMEOUT_S = 15.0

_VOICE_SYSTEM_SUFFIX = (
    "\n\n[Voice Mode] "
    "You are in a live voice conversation. Keep responses concise, "
    "conversational, and natural. Do NOT use markdown formatting, "
    "bullet points, headers, or code blocks — the user will hear "
    "your reply spoken aloud. Summarize tool results in plain spoken language. "
    "If the user asks to be reminded of something, schedule it using the reminder/cron tool "
    "and give a brief, friendly verbal confirmation."
)

_WORKING_HINT_ZH = "正在处理中，请稍等"

_WORKING_HINT_EN = "Let me look into that"

_FALLBACK_ZH = "抱歉，处理时出了点问题，请再试一次"

_FALLBACK_EN = "Sorry, something went wrong. Please try again"

_APPROVAL_HINT_ZH = "这个操作需要您在屏幕上确认"

_APPROVAL_HINT_EN = "This action requires your confirmation on screen"

_TOOL_STUCK_HINT_ZH = "刚才的操作连续失败，我先停下来了，您可以换个说法再试一次"

_TOOL_STUCK_HINT_EN = "That step kept failing, so I stopped. You can try again in a different way"

_HANDOFF_HINT_ZH = "这个任务需要较长时间，已转入后台继续处理，完成后会主动提醒您"

_HANDOFF_HINT_EN = "This task requires more time and has been moved to the background. I will notify you when it finishes"

_SPEECH_INTERRUPTED_NOTE = (
    "[Note: the user interrupted your previous spoken reply before it finished. "
    "Do not repeat what you already said; continue naturally or address their new input.]"
)

_INTERRUPT_TTL_S = 120.0

_model_rebuilt = False
