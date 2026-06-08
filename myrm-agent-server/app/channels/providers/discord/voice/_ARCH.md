# channels/providers/discord/voice/

## 架构概述

本目录模块说明。上级文档：[../../../../_ARCH.md](../../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Discord Voice Channel support. | ✅ |
| `follow.py` | 模块 | Voice follow-user orchestration. Automatically tracks configured Discord users across voice channels with handoff and reconciliation. """ | ✅ |
| `manager.py` | 模块 | High-level voice orchestration. Owns per-guild state and coordinates receiver/player lifecycle with follow-user support. """ | ✅ |
| `player.py` | 模块 | Voice audio output. Uses FFmpeg for format conversion and discord.py's built-in AudioSource pipeline. """ | ✅ |
| `receiver.py` | 模块 | Low-level voice packet processing. Runs on the SocketReader thread for packet capture, with check_silence() polled from async code. """ | ✅ |
