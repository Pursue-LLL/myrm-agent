"""Voice STT/TTS handling for inbound/outbound channel messages.

Transcribes incoming voice messages (STT) and optionally converts Agent
replies to audio (TTS). Supports Agent-driven TTS directives for
dynamic voice control.

[INPUT]
- channels.types::InboundMessage, (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)
- channels.core.bus::MessageBus (POS: async message bus)
- channels.voice.stt::transcribe, download_audio (POS: speech-to-text)
- channels.voice.tts::synthesize (POS: text-to-speech)

[OUTPUT]
- transcribe_inbound(): STT transcription of inbound voice
- download_inbound_audio(): download inbound voice attachment
- maybe_tts(): outbound TTS synthesis
- has_audio_attachment(): check whether message contains audio attachment
- parse_tts_directives(): parse Agent TTS directives
- strip_tts_tags(): strip TTS tags

[POS]
Voice processing module. Extracted from Router core routing logic as a collection
of pure/utility functions, invoked by AgentRouter during message processing.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from pathlib import Path

from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    TTSMode,
    VoiceConfig,
)

logger = logging.getLogger(__name__)

_TTS_DIRECTIVE_RE = re.compile(r"\[\[tts:([^\]]+)\]\]")
_TTS_TEXT_RE = re.compile(r"\[\[tts:text\]\](.*?)\[\[/tts:text\]\]", re.DOTALL)


def has_audio_attachment(msg: InboundMessage) -> bool:
    """Check if the message contains an audio/voice attachment."""
    return any(a.media_type == MediaType.AUDIO for a in msg.media)


def parse_tts_directives(text: str) -> tuple[dict[str, str], str | None]:
    """Extract TTS directives and optional TTS-only text block.

    Returns (directives_dict, tts_text_block_or_none).
    """
    directives: dict[str, str] = {}

    for match in _TTS_DIRECTIVE_RE.finditer(text):
        raw = match.group(1).strip()
        if raw == "off":
            directives["off"] = "true"
            continue
        if raw == "text":
            continue
        for part in raw.split():
            if "=" in part:
                key, _, val = part.partition("=")
                directives[key.strip()] = val.strip()

    tts_text_match = _TTS_TEXT_RE.search(text)
    tts_text = tts_text_match.group(1).strip() if tts_text_match else None

    return directives, tts_text


def strip_tts_tags(text: str) -> str:
    """Remove all TTS directive tags from text for display in chat."""
    text = _TTS_TEXT_RE.sub("", text)
    text = _TTS_DIRECTIVE_RE.sub("", text)
    return text.strip()


async def transcribe_inbound(
    msg: InboundMessage,
    voice_config: VoiceConfig | None,
    get_channel_fn: object,
) -> InboundMessage:
    """Transcribe voice attachments and inject transcript into content.

    Best-effort: returns original message unchanged on failure.

    Args:
        msg: Inbound message to transcribe.
        voice_config: Voice configuration (STT settings).
        get_channel_fn: Callable to get channel by name (MessageBus.get_channel).
    """
    if not voice_config or not voice_config.stt_enabled:
        return msg

    from app.channels.voice.stt import transcribe

    audio_path = await download_inbound_audio(msg, get_channel_fn)
    if not audio_path:
        return msg

    try:
        result = await transcribe(audio_path, voice_config)
    finally:
        audio_path.unlink(missing_ok=True)

    if not result or not result.text:
        return msg

    prefix = f"[ Voice] {result.text}"
    content = f"{prefix}\n{msg.content}" if msg.content else prefix
    logger.warning("Voice: STT transcribed %d chars from voice", len(result.text))
    return dataclasses.replace(msg, content=content)


async def download_inbound_audio(
    msg: InboundMessage,
    get_channel_fn: object,
) -> Path | None:
    """Download the voice attachment from the inbound message.

    Dispatches to the appropriate channel's download method.
    """
    from collections.abc import Callable

    assert callable(get_channel_fn)
    get_channel: Callable[[str], object | None] = get_channel_fn  # type: ignore[assignment]
    ch = get_channel(msg.channel)
    if not ch:
        return None

    if msg.channel == "whatsapp":
        voice_msg_id = msg.metadata.get("voice_message_id")
        if isinstance(voice_msg_id, str) and hasattr(ch, "download_voice_message"):
            return await ch.download_voice_message(voice_msg_id)  # type: ignore[union-attr]

    if msg.channel == "telegram":
        file_id = msg.metadata.get("voice_file_id")
        if isinstance(file_id, str) and hasattr(ch, "download_voice_message"):
            return await ch.download_voice_message(file_id)  # type: ignore[union-attr]

    for attachment in msg.media:
        if attachment.media_type == MediaType.AUDIO:
            if attachment.path:
                return Path(attachment.path)
            if attachment.url:
                from app.channels.voice.stt import download_audio

                return await download_audio(attachment.url)

    return None


async def maybe_tts(
    result: OutboundMessage,
    inbound_had_voice: bool,
    voice_config: VoiceConfig | None,
) -> OutboundMessage:
    """Optionally convert the Agent reply to audio based on TTS mode.

    Supports Agent-driven TTS directives in the reply:
    - ``[[tts:off]]`` — skip TTS for this reply
    - ``[[tts:voice=xxx]]`` — override voice
    - ``[[tts:provider=xxx]]`` — override provider
    - ``[[tts:text]]...[[/tts:text]]`` — TTS-only text (stripped from chat)

    Returns the original result if TTS is disabled or fails.
    """
    if not voice_config or voice_config.tts_mode == TTSMode.OFF:
        return result
    if voice_config.tts_mode == TTSMode.INBOUND and not inbound_had_voice:
        return result
    if not result.content:
        return result

    content = result.content
    directives, tts_text_block = parse_tts_directives(content)

    if directives.get("off"):
        return dataclasses.replace(result, content=strip_tts_tags(content))

    vc = voice_config
    overrides: dict[str, str | int | bool] = {}
    if "voice" in directives:
        overrides["tts_voice"] = directives["voice"]
    if "provider" in directives:
        overrides["tts_provider"] = directives["provider"]
    if overrides:
        vc = dataclasses.replace(vc, **overrides)

    tts_input = tts_text_block if tts_text_block else strip_tts_tags(content)
    clean_content = strip_tts_tags(content)

    from app.channels.voice.tts import synthesize

    audio_path = await synthesize(tts_input, vc)
    if not audio_path:
        return dataclasses.replace(result, content=clean_content)

    audio_attachment = MediaAttachment(
        media_type=MediaType.AUDIO,
        path=str(audio_path),
        mime_type="audio/mpeg",
    )
    logger.warning("Voice: TTS synthesized %s", audio_path.name)
    return dataclasses.replace(
        result,
        content=clean_content,
        media=result.media + (audio_attachment,),
    )
