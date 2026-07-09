# channels/providers/wechat/

## 架构概述

微信 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WeChat channel providers. | ✅ |
| `ilink_channel.py` | 模块 | WeChat personal account channel (iLink). Voice: platform ASR text when present; otherwise SILK→WAV via optional `wechat-silk` / `collect_issues` WARNING when pilk missing. | ✅ |
| `official_channel.py` | 模块 | WeChat Official Account channel implementation. Supports passive replies, customer service messages, rich-media (news) messages, and media send/receive. | ✅ |
