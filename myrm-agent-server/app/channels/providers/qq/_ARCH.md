# channels/providers/qq/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | QQ channel provider package. | ✅ |
| `api.py` | 模块 | QQ HTTP layer. Called by channel.py via self._api. """ | ✅ |
| `channel.py` | 模块 | QQ Official Bot channel. WebSocket real-time event reception, REST API message sending, 2-step rich media upload, msg_seq multi-reply management, group chat URL | ✅ |
| `helpers.py` | 模块 | app.channels.providers.qq.helpers — Pure helper functions for QQ channel. """ | ✅ |
