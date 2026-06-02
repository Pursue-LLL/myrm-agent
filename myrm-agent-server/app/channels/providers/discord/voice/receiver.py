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
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from collections import defaultdict
from collections.abc import Set

import discord.opus

logger = logging.getLogger(__name__)

_SILENCE_THRESHOLD = 1.5
_MIN_SPEECH_DURATION = 0.5
_SAMPLE_RATE = 48000
_CHANNELS = 2
_BYTES_PER_SECOND = _SAMPLE_RATE * _CHANNELS * 2


class VoiceReceiver:
    """Captures and decodes voice audio from a Discord voice channel.

    Attaches to a VoiceClient's socket listener, decrypts RTP packets
    using the negotiated mode, decodes Opus to PCM, and buffers per-user
    audio. A polling loop detects silence and delivers completed utterances.
    """

    def __init__(
        self,
        voice_client: object,
        allowed_user_ids: Set[str] | None = None,
    ) -> None:
        self._vc = voice_client
        self._allowed_user_ids: set[str] = (
            set(allowed_user_ids) if allowed_user_ids else set()
        )
        self._running = False

        self._secret_key: bytes = b""
        self._bot_ssrc: int = 0
        self._mode: str = ""

        self._ssrc_to_user: dict[int, int] = {}
        self._lock = threading.Lock()

        self._buffers: dict[int, bytearray] = defaultdict(bytearray)
        self._last_packet_time: dict[int, float] = {}

        self._decoders: dict[int, discord.opus.Decoder] = {}

        self._dave_session: object | None = None

        self._paused = False
        self._packet_count = 0

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        """Start listening for voice packets."""
        conn = self._vc._connection  # type: ignore[attr-defined]
        self._secret_key = bytes(conn.secret_key)
        self._bot_ssrc = conn.ssrc
        self._mode = getattr(conn, "mode", "") or getattr(self._vc, "mode", "")
        self._dave_session = getattr(conn, "dave_session", None)

        self._install_speaking_hook(conn)
        conn.add_socket_listener(self._on_packet)
        self._running = True
        logger.info(
            "VoiceReceiver started (bot_ssrc=%d, mode=%s, dave=%s)",
            self._bot_ssrc,
            self._mode,
            self._dave_session is not None,
        )

    def stop(self) -> None:
        """Stop listening and clean up all state."""
        self._running = False
        try:
            self._vc._connection.remove_socket_listener(self._on_packet)  # type: ignore[attr-defined]
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

    def _install_speaking_hook(self, conn: object) -> None:
        """Hook SPEAKING events (op 5) to map SSRC -> user_id."""
        original_hook = getattr(conn, "hook", None)
        receiver = self

        async def wrapped_hook(ws: object, msg: object) -> None:
            if isinstance(msg, dict) and msg.get("op") == 5:
                data = msg.get("d", {})
                ssrc = data.get("ssrc")
                user_id = data.get("user_id")
                if ssrc and user_id:
                    receiver._map_ssrc(int(ssrc), int(user_id))
            if original_hook:
                await original_hook(ws, msg)

        conn.hook = wrapped_hook
        try:
            ws = getattr(conn, "ws", None)
            if ws is not None:
                ws._hook = wrapped_hook
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

        if ssrc == self._bot_ssrc:
            return

        cc = first_byte & 0x0F
        has_extension = bool(first_byte & 0x10)
        has_padding = bool(first_byte & 0x20)

        is_rtpsize = "rtpsize" in self._mode or "aead" in self._mode
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
            decrypted = self._decrypt_payload(encrypted, header, bytes(nonce))
        except Exception:
            self._packet_count += 1
            if self._packet_count <= 5:
                logger.debug(
                    "Decrypt failed (packet #%d, mode=%s)",
                    self._packet_count,
                    self._mode,
                )
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

        if self._dave_session:
            decrypted = self._dave_decrypt(ssrc, decrypted)
            if decrypted is None:
                return

        try:
            if ssrc not in self._decoders:
                self._decoders[ssrc] = discord.opus.Decoder()
            pcm = self._decoders[ssrc].decode(decrypted)
            with self._lock:
                self._buffers[ssrc].extend(pcm)
                self._last_packet_time[ssrc] = time.monotonic()
        except Exception as e:
            logger.debug("Opus decode error for SSRC %d: %s", ssrc, e)

    def _decrypt_payload(self, encrypted: bytes, header: bytes, nonce: bytes) -> bytes:
        """Decrypt payload using the negotiated encryption mode."""
        import nacl.secret

        if "aead" in self._mode or "xchacha" in self._mode:
            box = nacl.secret.Aead(self._secret_key)
            return box.decrypt(encrypted, header, nonce)

        box = nacl.secret.SecretBox(self._secret_key)
        return box.decrypt(encrypted, nonce)

    def _dave_decrypt(self, ssrc: int, payload: bytes) -> bytes | None:
        """Decrypt DAVE E2EE layer if session is active."""
        with self._lock:
            user_id = self._ssrc_to_user.get(ssrc, 0)
        if not user_id:
            return payload

        try:
            import davey

            return self._dave_session.decrypt(  # type: ignore[union-attr]
                user_id, davey.MediaType.audio, payload
            )
        except Exception as e:
            if "Unencrypted" not in str(e):
                self._packet_count += 1
                if self._packet_count <= 5:
                    logger.debug("DAVE decrypt failed for ssrc=%d: %s", ssrc, e)
                return None
            return payload

    def _infer_user_for_ssrc(self, ssrc: int) -> int:
        """Infer user_id when SPEAKING event was missed (e.g. after rejoin)."""
        try:
            channel = self._vc.channel  # type: ignore[attr-defined]
            if not channel:
                return 0
            bot_id = self._vc.user.id if self._vc.user else 0  # type: ignore[attr-defined]
            candidates = [
                m.id
                for m in channel.members
                if m.id != bot_id
                and (not self._allowed_user_ids or str(m.id) in self._allowed_user_ids)
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

                if (
                    silence_duration >= _SILENCE_THRESHOLD
                    and buf_duration >= _MIN_SPEECH_DURATION
                ):
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
