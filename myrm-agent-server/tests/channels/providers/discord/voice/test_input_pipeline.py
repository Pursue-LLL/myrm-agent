"""Unit tests for VoiceInputPipeline."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.input_pipeline import (
    VoiceInputPipeline,
    _is_whisper_hallucination,
)


class TestWhisperHallucination:
    def test_common_hallucinations(self) -> None:
        assert _is_whisper_hallucination("Thanks for watching")
        assert _is_whisper_hallucination("thank you")
        assert _is_whisper_hallucination("...")
        assert _is_whisper_hallucination("bye")
        assert _is_whisper_hallucination("")
        assert _is_whisper_hallucination("  The end.  ")

    def test_real_speech(self) -> None:
        assert not _is_whisper_hallucination("Hello, how are you?")
        assert not _is_whisper_hallucination("What is the weather like?")
        assert not _is_whisper_hallucination("Thank you for helping me with this project")


class TestResolveDisplayName:
    def test_resolve_success(self) -> None:
        client = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.display_name = "TestUser"
        guild.get_member.return_value = member
        client.get_guild.return_value = guild

        pipeline = VoiceInputPipeline(client)
        name = pipeline._resolve_display_name(1, 42)
        assert name == "TestUser"

    def test_resolve_no_guild(self) -> None:
        client = MagicMock()
        client.get_guild.return_value = None

        pipeline = VoiceInputPipeline(client)
        name = pipeline._resolve_display_name(1, 42)
        assert name == "42"

    def test_resolve_no_member(self) -> None:
        client = MagicMock()
        guild = MagicMock()
        guild.get_member.return_value = None
        client.get_guild.return_value = guild

        pipeline = VoiceInputPipeline(client)
        name = pipeline._resolve_display_name(1, 42)
        assert name == "42"

    def test_resolve_exception(self) -> None:
        client = MagicMock()
        client.get_guild.side_effect = RuntimeError("fail")

        pipeline = VoiceInputPipeline(client)
        name = pipeline._resolve_display_name(1, 42)
        assert name == "42"


class TestProcess:
    @pytest.mark.asyncio
    async def test_process_full_pipeline(self) -> None:
        client = MagicMock()
        guild = MagicMock()
        member = MagicMock()
        member.display_name = "Alice"
        guild.get_member.return_value = member
        client.get_guild.return_value = guild

        cb = AsyncMock()
        pipeline = VoiceInputPipeline(client, on_voice_input=cb)

        pcm = b"\x00" * 3200

        mock_result = MagicMock()
        mock_result.text = "Hello world"

        with (
            patch.object(
                VoiceInputPipeline,
                "_resolve_display_name",
                return_value="Alice",
            ),
            patch("app.channels.providers.discord.voice.input_pipeline.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.input_pipeline.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "app.channels.types.VoiceConfig",
            ),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await pipeline.process(1, 42, pcm, 789)

        cb.assert_awaited_once()
        call_args = cb.call_args[0]
        assert call_args[0] == 789
        assert call_args[1] == 42
        assert call_args[2] == "Hello world"
        assert call_args[3] == "Alice"

    @pytest.mark.asyncio
    async def test_process_uses_guild_id_when_no_text_channel(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(client, on_voice_input=cb)

        mock_result = MagicMock()
        mock_result.text = "Test"

        with (
            patch.object(VoiceInputPipeline, "_resolve_display_name", return_value="Bob"),
            patch("app.channels.providers.discord.voice.input_pipeline.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.input_pipeline.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await pipeline.process(1, 42, b"\x00" * 3200, 0)

        cb.assert_awaited_once()
        assert cb.call_args[0][0] == 1

    @pytest.mark.asyncio
    async def test_process_hallucination_filtered(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(client, on_voice_input=cb)

        mock_result = MagicMock()
        mock_result.text = "Thanks for watching"

        with (
            patch.object(VoiceInputPipeline, "_resolve_display_name", return_value="X"),
            patch("app.channels.providers.discord.voice.input_pipeline.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.input_pipeline.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await pipeline.process(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_empty_result(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(client, on_voice_input=cb)

        mock_result = MagicMock()
        mock_result.text = ""

        with (
            patch("app.channels.providers.discord.voice.input_pipeline.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.input_pipeline.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await pipeline.process(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_no_result(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(client, on_voice_input=cb)

        with (
            patch("app.channels.providers.discord.voice.input_pipeline.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.input_pipeline.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await pipeline.process(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_exception(self) -> None:
        client = MagicMock()
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(client, on_voice_input=cb)

        with patch("app.channels.providers.discord.voice.input_pipeline.asyncio") as mock_asyncio:
            mock_asyncio.to_thread = AsyncMock(side_effect=RuntimeError("ffmpeg fail"))
            mock_asyncio.sleep = asyncio.sleep

            await pipeline.process(1, 42, b"\x00" * 3200, 0)

        cb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_process_no_callback(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, on_voice_input=None)

        mock_result = MagicMock()
        mock_result.text = "Hello"

        with (
            patch.object(VoiceInputPipeline, "_resolve_display_name", return_value="X"),
            patch("app.channels.providers.discord.voice.input_pipeline.VoiceReceiver"),
            patch("app.channels.providers.discord.voice.input_pipeline.asyncio") as mock_asyncio,
            patch(
                "app.channels.voice.stt.transcribe",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch("app.channels.types.VoiceConfig"),
        ):
            mock_asyncio.to_thread = AsyncMock()
            mock_asyncio.sleep = asyncio.sleep

            await pipeline.process(1, 42, b"\x00" * 3200, 0)


async def _process(pipeline: VoiceInputPipeline, transcript: str) -> None:
    """Run one utterance through ``pipeline`` with speech-to-text answering ``transcript``."""
    result = MagicMock()
    result.text = transcript
    with (
        patch("app.channels.providers.discord.voice.input_pipeline.asyncio.to_thread", new_callable=AsyncMock),
        patch("app.channels.voice.stt.transcribe", new_callable=AsyncMock, return_value=result),
        patch("app.channels.types.VoiceConfig"),
    ):
        await pipeline.process(1, 42, b"\x00" * 3200, 0)


class TestProcessGates:
    @pytest.mark.asyncio
    async def test_speech_without_the_wake_word_is_dropped_while_asleep(self) -> None:
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(MagicMock(), on_voice_input=cb, wake_words=["hey bot"])

        await _process(pipeline, "what is the time")
        cb.assert_not_awaited()

        await _process(pipeline, "hey bot what is the time")
        cb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_speech_after_the_wake_word_passes_within_the_wake_window(self) -> None:
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(MagicMock(), on_voice_input=cb, wake_words=["hey bot"])

        await _process(pipeline, "hey bot hello")
        await _process(pipeline, "what is the time")

        assert cb.await_count == 2

    @pytest.mark.asyncio
    async def test_the_echo_of_the_bots_playback_is_dropped_and_a_real_interruption_stops_it(self) -> None:
        cb = AsyncMock()
        pipeline = VoiceInputPipeline(MagicMock(), on_voice_input=cb, barge_in_enabled=True)
        player = MagicMock()
        player.is_playing = True
        pipeline.register_player(1, player, "Hello world how are you today")

        await _process(pipeline, "Hello world how are you today")
        cb.assert_not_awaited()
        player.stop.assert_not_called()

        await _process(pipeline, "Stop please")
        cb.assert_awaited_once()
        player.stop.assert_called_once()


class TestBargeIn:
    def test_barge_in_echo_detected(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, barge_in_enabled=True)
        player = MagicMock()
        player.is_playing = True
        pipeline._active_players[1] = player
        pipeline._active_play_texts[1] = "Hello world how are you today"
        result = pipeline._handle_barge_in(1, "Hello world how are you today", "hello world how are you today")
        assert result is True

    def test_barge_in_real_interruption(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, barge_in_enabled=True)
        player = MagicMock()
        player.is_playing = True
        player.stop = MagicMock()
        pipeline._active_players[1] = player
        pipeline._active_play_texts[1] = "Hello world"
        result = pipeline._handle_barge_in(1, "Stop please", "stop please")
        assert result is False
        player.stop.assert_called_once()

    def test_barge_in_no_player(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, barge_in_enabled=True)
        result = pipeline._handle_barge_in(1, "Test", "test")
        assert result is False


class TestWakeWord:
    def test_wake_word_activates(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, wake_words=["hey bot"])
        result = pipeline._check_wake_word(1, "hey bot what is the time")
        assert result is True
        assert pipeline._wake_until.get(1, 0) > 0

    def test_wake_word_asleep_no_match(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, wake_words=["hey bot"])
        result = pipeline._check_wake_word(1, "what is the time")
        assert result is False

    def test_wake_word_stays_awake_within_ttl(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, wake_words=["hey bot"])
        pipeline._wake_until[1] = time.time() + 30
        result = pipeline._check_wake_word(1, "what is the time")
        assert result is True

    def test_wake_word_non_ascii(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, wake_words=["\u5c0f\u52a9\u624b"])
        result = pipeline._check_wake_word(1, "\u5c0f\u52a9\u624b\u5e2e\u6211\u67e5\u5929\u6c14")
        assert result is True

    def test_wake_word_ascii_boundary(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, wake_words=["bot"])
        assert pipeline._check_wake_word(1, "hey bot how are you") is True
        pipeline._wake_until.clear()
        assert pipeline._check_wake_word(1, "robot is here") is False


class TestRegisterUnregisterPlayer:
    def test_register_player(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client)
        player = MagicMock()
        pipeline.register_player(1, player, "hello world")
        assert pipeline._active_players[1] is player
        assert pipeline._active_play_texts[1] == "hello world"

    def test_unregister_player(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client)
        pipeline._active_players[1] = MagicMock()
        pipeline._active_play_texts[1] = "text"
        pipeline.unregister_player(1)
        assert 1 not in pipeline._active_players
        assert 1 not in pipeline._active_play_texts

    def test_unregister_nonexistent(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client)
        pipeline.unregister_player(999)


class TestBargeInStopException:
    def test_barge_in_stop_exception_handled(self) -> None:
        client = MagicMock()
        pipeline = VoiceInputPipeline(client, barge_in_enabled=True)
        player = MagicMock()
        player.is_playing = True
        player.stop = MagicMock(side_effect=RuntimeError("stop failed"))
        pipeline._active_players[1] = player
        pipeline._active_play_texts[1] = "Hello world"
        result = pipeline._handle_barge_in(1, "Stop please", "stop please")
        assert result is False
