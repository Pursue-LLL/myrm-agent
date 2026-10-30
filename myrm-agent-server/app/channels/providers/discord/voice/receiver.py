"""Discord Voice Receiver - RTP decryption, DAVE E2EE, SSRC mapping, VAD, PCM buffering.

Attaches to a discord.py VoiceClient's socket listener, decrypts
RTP packets (NaCl transport + optional DAVE E2EE) using the negotiated
encryption mode, decodes Opus to PCM, and buffers per-user audio.
Silence detection delivers completed utterances.

[INPUT]
- discord.VoiceClient (POS: Discord voice connection)

[OUTPUT]
- VoiceReceiver: class - captures and decodes voice audio

[POS]
Low-level voice packet processing. Runs on the SocketReader thread
for packet capture, with check_silence() polled from async code.
The transport key, the mode, the DAVE session and the bot's SSRC are read from the connection for every packet:
discord.py replaces them when the connection is re-established or upgraded, and keeps delivering packets meanwhile.
A run of packets that fail to decrypt is reported once as a warning, not once per packet.
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from collections import defaultdict
from collections.abc import Set
from typing import TYPE_CHECKING, NamedTuple

import discord.opus

if TYPE_CHECKING:
    import davey
    from discord import VoiceClient
    from discord.gateway import DiscordVoiceWebSocket
    from discord.voice_state import VoiceConnectionState

logger = logging.getLogger(__name__)

_SILENCE_THRESHOLD = 1.5
_MIN_SPEECH_DURATION = 0.5
_SAMPLE_RATE = 48000
_CHANNELS = 2
_BYTES_PER_SECOND = _SAMPLE_RATE * _CHANNELS * 2

# Consecutive packets that fail to decrypt before the receiver says so: about a second of one speaker's audio.
_UNDECRYPTABLE_STREAK_WARNING = 50


class _Credentials(NamedTuple):
    """What the connection holds for decrypting audio at the moment a packet arrives."""

    secret_key: bytes
    mode: str
    bot_ssrc: int
    dave_session: davey.DaveSession | None


class VoiceReceiver:
    """Captures and decodes voice audio from a Discord voice channel.

    Attaches to a VoiceClient's socket listener, decrypts RTP packets
    using the negotiated mode, decodes Opus to PCM, and buffers per-user
    audio. A polling loop detects silence and delivers completed utterances.
    """

    def __init__(
        self,
        voice_client: VoiceClient,
        allowed_user_ids: Set[str] | None = None,
    ) -> None:
        self._vc = voice_client
        self._allowed_user_ids: set[str] = set(allowed_user_ids) if allowed_user_ids else set()
        self._running = False

        self._ssrc_to_user: dict[int, int] = {}
        self._lock = threading.Lock()

        self._buffers: dict[int, bytearray] = defaultdict(bytearray)
        self._last_packet_time: dict[int, float] = {}

        self._decoders: dict[int, discord.opus.Decoder] = {}

        self._paused = False
        self._undecryptable_streak = 0

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start listening for voice packets."""
        conn = self._vc._connection
        self._install_speaking_hook(conn)
        conn.add_socket_listener(self._on_packet)
        self._running = True
        credentials = self._credentials()
        logger.info(
            "VoiceReceiver started (mode=%s, dave=%s)",
            credentials.mode if credentials else "pending",
            credentials is not None and credentials.dave_session is not None,
        )

    def _credentials(self) -> _Credentials | None:
        """The connection's decryption credentials as they are now, or None until its session has a key."""
        conn = self._vc._connection
        key = conn.secret_key
        if not key:
            return None
        return _Credentials(bytes(key), conn.mode, conn.ssrc, conn.dave_session)

    def stop(self) -> None:
        """Stop listening and clean up all state."""
        self._running = False
        try:
            self._vc._connection.remove_socket_listener(self._on_packet)
        except Exception:
            pass
        with self._lock:
            self._buffers.clear()
            self._last_packet_time.clear()
            self._decoders.clear()
            self._ssrc_to_user.clear()
        logger.info("VoiceReceiver stopped")

    def pause(self) -> None:
        """Pause packet capture (during TTS playback to prevent echo)."""
        self._paused = True

    def resume(self) -> None:
        """Resume packet capture after playback."""
        self._paused = False

    def _install_speaking_hook(self, conn: VoiceConnectionState) -> None:
        """Hook SPEAKING events (op 5) to map SSRC -> user_id."""
        original_hook = conn.hook
        receiver = self

        async def wrapped_hook(ws: DiscordVoiceWebSocket, msg: dict[str, object]) -> None:
            data = msg.get("d")
            if msg.get("op") == 5 and isinstance(data, dict):
                ssrc = data.get("ssrc")
                user_id = data.get("user_id")
                if ssrc and user_id:
                    receiver._map_ssrc(int(ssrc), int(user_id))
            if original_hook:
                await original_hook(ws, msg)

        conn.hook = wrapped_hook
        try:
            ws = conn.ws
            if ws is not None:
                ws._hook = wrapped_hook  # type: ignore[method-assign]
        except Exception:
            pass

    def _map_ssrc(self, ssrc: int, user_id: int) -> None:
        with self._lock:
            self._ssrc_to_user[ssrc] = user_id

    def _on_packet(self, data: bytes) -> None:
        """Process a raw UDP packet from the voice socket."""
        if not self._running or self._paused:
            return

        if len(data) < 16:
            return

        if (data[0] >> 6) != 2 or (data[1] & 0x7F) != 0x78:
            return

        first_byte = data[0]
        _, _, _seq, _timestamp, ssrc = struct.unpack_from(">BBHII", data, 0)

        credentials = self._credentials()
        if credentials is None or ssrc == credentials.bot_ssrc:
            return

        cc = first_byte & 0x0F
        has_extension = bool(first_byte & 0x10)
        has_padding = bool(first_byte & 0x20)

        is_rtpsize = "rtpsize" in credentials.mode or "aead" in credentials.mode
        if is_rtpsize:
            header_size = 12 + (4 * cc) + (4 if has_extension else 0)
        else:
            header_size = 12

        if len(data) < header_size + 4:
            return

        ext_data_len = 0
        if has_extension and is_rtpsize:
            ext_preamble_offset = 12 + (4 * cc)
            ext_words = struct.unpack_from(">H", data, ext_preamble_offset + 2)[0]
            ext_data_len = ext_words * 4

        header = bytes(data[:header_size])
        payload_with_nonce = data[header_size:]

        if len(payload_with_nonce) < 4:
            return

        nonce = bytearray(24)
        nonce[:4] = payload_with_nonce[-4:]
        encrypted = bytes(payload_with_nonce[:-4])

        try:
            decrypted = self._decrypt_payload(credentials, encrypted, header, bytes(nonce))
        except Exception as exc:
            self._note_undecryptable("transport", credentials.mode, exc)
            return

        if ext_data_len and len(decrypted) > ext_data_len:
            decrypted = decrypted[ext_data_len:]

        if has_padding:
            if not decrypted:
                return
            pad_len = decrypted[-1]
            if pad_len == 0 or pad_len > len(decrypted):
                return
            decrypted = decrypted[:-pad_len]
            if not decrypted:
                return

        if credentials.dave_session:
            try:
                decrypted = self._dave_decrypt(credentials.dave_session, ssrc, decrypted)
            except Exception as exc:
                self._note_undecryptable("DAVE", credentials.mode, exc)
                return
        self._undecryptable_streak = 0

        try:
            if ssrc not in self._decoders:
                self._decoders[ssrc] = discord.opus.Decoder()  # type: ignore[no-untyped-call]
            pcm = self._decoders[ssrc].decode(decrypted, fec=False)
            with self._lock:
                self._buffers[ssrc].extend(pcm)
                self._last_packet_time[ssrc] = time.monotonic()
        except Exception as e:
            logger.debug("Opus decode error for SSRC %d: %s", ssrc, e)

    def _decrypt_payload(self, credentials: _Credentials, encrypted: bytes, header: bytes, nonce: bytes) -> bytes:
        """Decrypt payload using the negotiated encryption mode."""
        import nacl.secret

        if "aead" in credentials.mode or "xchacha" in credentials.mode:
            return nacl.secret.Aead(credentials.secret_key).decrypt(encrypted, header, nonce)

        return nacl.secret.SecretBox(credentials.secret_key).decrypt(encrypted, nonce)

    def _dave_decrypt(self, dave_session: davey.DaveSession, ssrc: int, payload: bytes) -> bytes:
        """Decrypt the DAVE E2EE layer; a frame DAVE reports as unencrypted, or from an unmapped SSRC, passes through."""
        with self._lock:
            user_id = self._ssrc_to_user.get(ssrc, 0)
        if not user_id:
            return payload

        import davey

        try:
            return dave_session.decrypt(user_id, davey.MediaType.audio, payload)
        except Exception as exc:
            if "Unencrypted" in str(exc):
                return payload
            raise

    def _note_undecryptable(self, stage: str, mode: str, exc: Exception) -> None:
        """Count one packet that failed to decrypt; a run of ``_UNDECRYPTABLE_STREAK_WARNING`` is reported once."""
        self._undecryptable_streak += 1
        if self._undecryptable_streak == _UNDECRYPTABLE_STREAK_WARNING:
            logger.warning(
                "Voice audio failed %s decryption for %d packets in a row (mode=%s, last error: %s); "
                "the voice session may need to be rejoined",
                stage,
                _UNDECRYPTABLE_STREAK_WARNING,
                mode,
                type(exc).__name__,
            )

    def _infer_user_for_ssrc(self, ssrc: int) -> int:
        """Infer user_id when SPEAKING event was missed (e.g. after rejoin)."""
        try:
            channel = self._vc.channel
            if not channel:
                return 0
            bot_id = self._vc.user.id if self._vc.user else 0
            candidates = [
                m.id
                for m in channel.members
                if m.id != bot_id and (not self._allowed_user_ids or str(m.id) in self._allowed_user_ids)
            ]
            if len(candidates) == 1:
                uid = candidates[0]
                self._ssrc_to_user[ssrc] = uid
                logger.info("Auto-mapped ssrc=%d -> user=%d", ssrc, uid)
                return uid
        except Exception:
            pass
        return 0

    def check_silence(self) -> list[tuple[int, bytes]]:
        """Return completed utterances as (user_id, pcm_bytes) pairs.

        An utterance is complete when silence exceeds _SILENCE_THRESHOLD
        and the buffered audio is longer than _MIN_SPEECH_DURATION.
        """
        now = time.monotonic()
        completed: list[tuple[int, bytes]] = []

        with self._lock:
            ssrc_user_map = dict(self._ssrc_to_user)
            ssrc_list = list(self._buffers.keys())

            for ssrc in ssrc_list:
                last_time = self._last_packet_time.get(ssrc, now)
                silence_duration = now - last_time
                buf = self._buffers[ssrc]
                buf_duration = len(buf) / _BYTES_PER_SECOND

                if silence_duration >= _SILENCE_THRESHOLD and buf_duration >= _MIN_SPEECH_DURATION:
                    user_id = ssrc_user_map.get(ssrc, 0)
                    if not user_id:
                        user_id = self._infer_user_for_ssrc(ssrc)
                    if user_id:
                        completed.append((user_id, bytes(buf)))
                    self._buffers[ssrc] = bytearray()
                    self._last_packet_time.pop(ssrc, None)
                elif silence_duration >= _SILENCE_THRESHOLD * 2:
                    self._buffers.pop(ssrc, None)
                    self._last_packet_time.pop(ssrc, None)

        return completed

    @staticmethod
    def pcm_to_wav_bytes(
        pcm_data: bytes,
        src_rate: int = _SAMPLE_RATE,
        src_channels: int = _CHANNELS,
    ) -> bytes:
        """Convert raw PCM to 48kHz mono or stereo WAV bytes in memory."""
        import io
        import wave

        # If we need 16kHz mono, we should downsample. But Whisper works fine with 48kHz stereo,
        # it downsamples internally via librosa or similar. To be safe and save memory,
        # let's just write the raw 48kHz PCM as a WAV file.
        # However, to save bandwidth for API calls, downsampling to 16kHz mono is better.
        # But doing high-quality downsampling in pure Python is slow.
        # OpenAI and Deepgram both support 48kHz files directly and downsample internally.
        # For true 0-dependency, we just wrap the raw PCM in a WAV container.

        with io.BytesIO() as wav_io:
            with wave.open(wav_io, "wb") as wav_file:
                wav_file.setnchannels(src_channels)
                wav_file.setsampwidth(2)  # 16-bit PCM = 2 bytes
                wav_file.setframerate(src_rate)
                wav_file.writeframes(pcm_data)
            return wav_io.getvalue()
