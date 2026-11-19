"""Core TTS generation engine.

[INPUT]
- httpx (POS: Async HTTP client)
- models::TTSConfig, TTSResult, TTSGenerationError, MediaMeta (POS: Data models)

[OUTPUT]
- AsyncTTSEngine: Core TTS generation engine

[POS]
Handles HTTP requests to TTS providers (OpenAI, ElevenLabs, Volcengine
Doubao-TTS / Seed-Audio) with Try-Catch flexible fallback for gateway
routing. Volcengine OpenSpeech endpoints are not proxied by the gateway
and always connect directly via tts/volcengine.py.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import replace

from myrm_agent_harness.infra.tls_compat import create_httpx_client

from .models import (
    MediaMeta,
    TTSConfig,
    TTSGenerationError,
    TTSResult,
)

logger = logging.getLogger(__name__)


class AsyncTTSEngine:
    """Async TTS generation engine."""

    def __init__(self, config: TTSConfig) -> None:
        self.config = config

    async def generate(self, text: str, *, style: str | None = None) -> TTSResult:
        """Generate speech from text with an optional speaking style directive."""
        max_attempts = self.config.max_retries + 1
        bypass_gateway = False
        last_error: Exception | None = None
        start_time = time.time()

        for attempt in range(max_attempts):
            try:
                result = await self._call_provider(text, bypass_gateway=bypass_gateway, style=style)
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()

                if (
                    not bypass_gateway
                    and self.config.provider != "volcengine"
                    and self.config.gateway_config
                    and self.config.gateway_config.use_gateway
                    and self.config.api_key
                ) and (
                    "502" in error_msg
                    or "503" in error_msg
                    or "504" in error_msg
                    or "402" in error_msg
                    or "insufficient" in error_msg
                    or "timeout" in error_msg
                ):
                    logger.warning(
                        "Gateway TTS failed (%s), falling back to direct provider API (BYOK)",
                        error_msg,
                    )
                    bypass_gateway = True
                    continue

                if attempt < max_attempts - 1:
                    await asyncio.sleep(1.0 * (2**attempt))
            else:
                # Outside the try: a storage failure is not a provider failure, so it is never retried.
                return await self._persist(result, text)

        latency_ms = (time.time() - start_time) * 1000
        raise TTSGenerationError(
            f"TTS generation failed after {max_attempts} attempts. Last error: {last_error}",
            latency_ms=latency_ms,
        )

    async def _call_provider(
        self,
        text: str,
        bypass_gateway: bool,
        style: str | None = None,
    ) -> TTSResult:
        start_time = time.time()
        provider = self.config.provider

        if provider == "volcengine":
            # The unified gateway does not proxy Volcengine OpenSpeech
            # endpoints; always connect directly with the Volcengine protocol.
            from .volcengine import (
                build_volcengine_request,
                parse_volcengine_response,
                resolve_volcengine_timeout,
            )

            request = build_volcengine_request(self.config, text, style)
            async with create_httpx_client(timeout=resolve_volcengine_timeout(self.config)) as client:
                response = await client.post(request.url, headers=request.headers, json=request.payload)
                response.raise_for_status()
                audio_bytes, mime_type, duration_seconds = await parse_volcengine_response(
                    request, response, self.config
                )
        else:
            url, headers, payload = self._build_request(text, bypass_gateway)

            async with create_httpx_client(timeout=self.config.timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                audio_bytes = response.content
                mime_type = response.headers.get("content-type", "audio/mpeg")
                duration_seconds = None

        latency_ms = (time.time() - start_time) * 1000

        return TTSResult(
            audio_bytes=audio_bytes,
            mime_type=mime_type,
            provider=provider,
            model=self.config.model,
            latency_ms=latency_ms,
            duration_seconds=duration_seconds,
        )

    async def _persist(self, result: TTSResult, text: str) -> TTSResult:
        """Store the audio through the media callback and attach its stable reference.

        Fail-closed: with a callback configured, audio that cannot be stored (callback error, empty reference) is a
        failed generation. Without one the result is returned as the provider gave it.
        """
        callback = self.config.media_callback
        if callback is None:
            return result
        try:
            reference = await callback(
                result.audio_bytes,
                result.mime_type,
                MediaMeta(prompt=text, model=result.model, provider=result.provider),
            )
            if not reference:
                raise ValueError("the media callback returned an empty reference")
        except Exception as exc:
            raise TTSGenerationError(
                f"Failed to store the generated audio: {exc}", latency_ms=result.latency_ms
            ) from exc
        return replace(result, persisted_ref=reference)

    def _build_request(self, text: str, bypass_gateway: bool) -> tuple[str, dict[str, str], dict[str, object]]:
        provider = self.config.provider

        if not bypass_gateway and self.config.gateway_config and self.config.gateway_config.use_gateway:
            base_url = (self.config.gateway_config.gateway_url or "").rstrip("/")
            if provider == "openai":
                url = f"{base_url}/tts/openai/{self.config.model}"
            elif provider == "elevenlabs":
                url = f"{base_url}/tts/elevenlabs/{self.config.voice}"
            else:
                url = f"{base_url}/tts/{provider}/{self.config.model}"

            headers = {
                "Authorization": f"Bearer {self.config.gateway_config.auth_token}",
                "Content-Type": "application/json",
            }
        else:
            api_key = self.config.api_key.get_secret_value() if self.config.api_key else ""
            if provider == "openai":
                url = self.config.base_url or "https://api.openai.com/v1/audio/speech"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
            elif provider == "elevenlabs":
                url = self.config.base_url or f"https://api.elevenlabs.io/v1/text-to-speech/{self.config.voice}"
                headers = {
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                }
            else:
                raise ValueError(f"Unsupported TTS provider: {provider}")

        payload: dict[str, object]
        if provider == "openai":
            payload = {
                "model": self.config.model,
                "input": text,
                "voice": self.config.voice,
                "speed": self.config.speed,
            }
        elif provider == "elevenlabs":
            payload = {
                "model_id": self.config.model,
                "text": text,
            }
        else:
            payload = {"text": text}

        return url, headers, payload
