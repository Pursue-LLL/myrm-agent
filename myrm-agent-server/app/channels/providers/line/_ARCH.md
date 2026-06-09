# channels/providers/line/

## 架构概述

LINE 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | LINE channel provider via Messaging API. | ✅ |
| `api.py` | 模块 | LINE HTTP layer. Called by channel.py via self._api. | ✅ |
| `channel.py` | 模块 | LINE integration: webhook inbound, Reply/Push outbound, mention detection, quote-token context linking. | ✅ |
| `helpers.py` | 模块 | LINE webhook type definitions and constants. Referenced by channel.py. | ✅ |
