# channels/providers/signal/

## 架构概述

Signal 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Signal channel provider via Signal CLI REST API. | ✅ |
| `api.py` | 模块 | Signal HTTP/WS layer. Provides REST messaging, WebSocket stream_events(), and HTTP polling fallback. Called by channel.py via self._api. | ✅ |
| `channel.py` | 模块 | Signal integration. Implemented via Signal CLI REST API: credentials, lifecycle, inbound mode selection, outbound, groups and diagnostics; composes `SignalInboundMixin`. | ✅ |
| `helpers.py` | 模块 | Signal envelope type definitions, constants (timeouts, WS settings), and pure functions. Referenced by channel.py, inbound.py and api.py. | ✅ |
| `inbound.py` | 模块 | `SignalInboundMixin`: WebSocket / HTTP polling receive loops, envelope routing, reaction and data-message parsing, mention and attachment handling. | ✅ |
