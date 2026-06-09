# channels/providers/discord/

## 架构概述

Discord 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Discord channel provider. | ✅ |
| `channel.py` | 模块 | Discord channel implementation with Forum channel support. | ✅ |
| `config.py` | 模块 | Discord channel configuration. | ✅ |
| `helpers.py` | 模块 | Pure-function helpers for the Discord channel. Converts framework message objects to Discord native objects. | ✅ |
