# channels/providers/onebot/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | OneBot v11 Channel Provider. | ✅ |
| `channel.py` | 模块 | OneBot v11 channel adapter. Runs as a WebSocket Reverse Server, accepting connections from clients like NapCatQQ and go-cqhttp, enabling QQ personal/group messa | ✅ |
| `helpers.py` | 模块 | Pure-function helpers for the OneBot channel. Handles bidirectional conversion between OneBot v11 message segments and framework message objects. """ | ✅ |
