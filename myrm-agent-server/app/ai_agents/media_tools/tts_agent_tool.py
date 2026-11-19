"""[INPUT]
- myrm_agent_harness.toolkits.llms.tts.generator::AsyncTTSEngine (POS: TTS synthesis engine)
- myrm_agent_harness.toolkits.llms.tts.models::TTSConfig (POS: TTS engine config)

[OUTPUT]
- create_tts_tool(): LangChain BaseTool adapter for text-to-speech

[POS]
LangChain adapter for harness AsyncTTSEngine (product layer). The engine stores the audio before it answers, and the
result carries the audio's ``media://`` reference: the call reports success only with a stored reference.
"""

from __future__ import annotations

import json
import logging

from langchain_core.callbacks import CallbackManagerForToolRun
from langchain_core.tools import BaseTool
from myrm_agent_harness.toolkits.llms.tts.generator import AsyncTTSEngine
from myrm_agent_harness.toolkits.llms.tts.models import TTSConfig
from pydantic import BaseModel, Field, PrivateAttr

logger = logging.getLogger(__name__)

MAX_TTS_TEXT_LENGTH = 1500


class TTSInput(BaseModel):
    """Input schema for TTS tool."""

    text: str = Field(
        ...,
        description="The plain text content to synthesize into spoken audio. For optimal latency and natural prosody, keep text concise (under 1500 characters).",
    )
    style: str | None = Field(
        default=None,
        description=(
            "Optional speaking style directive for expressive narration, e.g. "
            "'cheerful and energetic' or 'calm and soothing'. Write it as a short natural-language "
            "phrase. Applied only when the Volcengine Seed-Audio voice is configured; other providers "
            "ignore it and use their default tone."
        ),
    )


def _error(message: str) -> str:
    return json.dumps({"status": "error", "error": message}, ensure_ascii=False)


class TTSTool(BaseTool):
    """Tool for generating speech from text."""

    name: str = "tts_generate"
    description: str = (
        "Generate natural spoken speech (audio) from text. "
        "Use this when the user asks to read something out loud, synthesize voice narration, or generate a voice message. "
        "The audio appears in the chat by itself, so never repeat its media:// address in your reply."
    )
    args_schema: type[BaseModel] = TTSInput

    config: TTSConfig = Field(exclude=True)
    _engine: AsyncTTSEngine = PrivateAttr()

    def __init__(self, config: TTSConfig) -> None:
        super().__init__(config=config)
        self._engine = AsyncTTSEngine(config)

    def _run(
        self,
        text: str,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Synchronous run is not supported."""
        raise NotImplementedError("TTSTool only supports async execution.")

    async def _arun(
        self,
        text: str,
        style: str | None = None,
        run_manager: CallbackManagerForToolRun | None = None,
    ) -> str:
        """Asynchronously generate speech."""
        cleaned_text = text.strip()
        if not cleaned_text:
            return _error("Text content cannot be empty.")

        if len(cleaned_text) > MAX_TTS_TEXT_LENGTH:
            return _error(
                f"Text length ({len(cleaned_text)} characters) exceeds the safe single-turn limit "
                f"of {MAX_TTS_TEXT_LENGTH} characters. Please summarize or chunk the text into smaller segments."
            )

        try:
            # Clamp style directives: Seed-Audio wraps them into a bounded text prompt.
            effective_style = (style or "").strip()[:200] or None
            result = await self._engine.generate(cleaned_text, style=effective_style)
        except Exception as e:
            logger.error("TTS generation failed: %s", e)
            return _error(f"TTS generation failed: {e}")

        if not result.persisted_ref:
            return _error("TTS generation failed: the audio was not stored")

        out: dict[str, object] = {
            "status": "success",
            "provider": result.provider,
            "model": result.model,
            "latency_ms": round(result.latency_ms),
            "audio_url": result.persisted_ref,
            "message": "Audio generated; it appears in the chat for the user to play.",
        }
        if result.duration_seconds is not None:
            out["duration_seconds"] = round(result.duration_seconds, 1)
        return json.dumps(out, ensure_ascii=False)


def create_tts_tool(config: TTSConfig) -> TTSTool:
    """Wrap an AsyncTTSEngine config as a LangChain tool named ``tts_generate``."""
    return TTSTool(config)
