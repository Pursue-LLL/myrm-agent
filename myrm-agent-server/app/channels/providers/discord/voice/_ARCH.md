# channels/providers/discord/voice/

## 架构概述

Discord 语音 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Discord Voice Channel support. | ✅ |
| `follow.py` | 模块 | Voice follow-user orchestration. Automatically tracks configured Discord users across voice channels with handoff and reconciliation. A followed user may be in a voice or a stage channel (`VoiceTarget`). | ✅ |
| `input_pipeline.py` | 模块 | Speech-input gate of the voice manager. One finished utterance goes PCM to WAV to speech-to-text, past the hallucination filter, the echo/barge-in check and the wake-word gate, and reaches the voice-input callback with the speaker's display name. Owns the playback registry that echo detection compares against and each guild's wake-up window. | ✅ |
| `manager.py` | 模块 | High-level voice orchestration. Owns per-guild state and coordinates receiver/player lifecycle with follow-user support; each finished utterance from a speaker the speaker gate admits is handed to the input pipeline, and a refused speaker's audio never reaches speech-to-text (the first refusal of a speaker in a session is logged; with no gate wired no speaker is admitted). Leaving every guild is concurrent, so one guild that waits for the gateway's confirmation does not hold up the others. A join over a session whose VoiceClient discord.py has dropped releases that session first; over one discord.py is still reconnecting, the join is declined. A leave disconnects the VoiceClient for as long as discord.py holds it, connected or not. The utterances finished in one poll keep the text-channel binding they were admitted under. | ✅ |
| `player.py` | 模块 | Voice audio output. Uses FFmpeg for format conversion and discord.py's built-in AudioSource pipeline. | ✅ |
| `receiver.py` | 模块 | Low-level voice packet processing. Runs on the SocketReader thread for packet capture, with check_silence() polled from async code. The transport key, the mode, the DAVE session and the bot's SSRC are read from the connection for every packet: discord.py replaces them when the connection is re-established or upgraded, and keeps delivering packets meanwhile. A run of packets that fail to decrypt is reported once as a warning, not once per packet. | ✅ |
