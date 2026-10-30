# channels/providers/discord/voice/

## 架构概述

Discord 语音 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Discord Voice Channel support. | ✅ |
| `follow.py` | 模块 | Voice follow-user orchestration. Automatically tracks configured Discord users across voice channels with handoff and reconciliation. A followed user may be in a voice or a stage channel (`VoiceTarget`). | ✅ |
| `manager.py` | 模块 | High-level voice orchestration. Owns per-guild state and coordinates receiver/player lifecycle with follow-user support. Leaving every guild is concurrent, so one guild that waits for the gateway's confirmation does not hold up the others. A join over a session whose VoiceClient discord.py has dropped releases that session first; over one discord.py is still reconnecting, the join is declined. | ✅ |
| `player.py` | 模块 | Voice audio output. Uses FFmpeg for format conversion and discord.py's built-in AudioSource pipeline. | ✅ |
| `receiver.py` | 模块 | Low-level voice packet processing. Runs on the SocketReader thread for packet capture, with check_silence() polled from async code. | ✅ |
