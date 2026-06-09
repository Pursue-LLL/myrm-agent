# channels/providers/googlechat/

## 架构概述

Google Chat 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Google Chat channel provider. | ✅ |
| `api.py` | 模块 | app.channels.providers.googlechat.api — Google Chat API client with Service Account JWT auth. | ✅ |
| `channel.py` | 模块 | app.channels.providers.googlechat.channel — Google Chat Webhook-based bidirectional messaging. | ✅ |
