# channels/providers/googlechat/

## 架构概述

Google Chat 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Google Chat channel provider. | ✅ |
| `api.py` | 模块 | app.channels.providers.googlechat.api — Google Chat API client with Service Account JWT auth. `send_message` and `update_message` are the only paths that carry message text, and both pass it through `defuse_all_mention()`. | ✅ |
| `channel.py` | 模块 | app.channels.providers.googlechat.channel — Google Chat Webhook-based bidirectional messaging. | ✅ |
| `mentions.py` | 模块 | Defuse mention-everyone markup in text bound for a Google Chat space. `defuse_all_mention()` puts a zero-width space after the `<` of `<users/all>` (Chat markup) and `<chat-user data-user="users/all">` (Markdown syntax), in any case and either quote style; `<users/123>`, `<users/allen>` and `<users/all_hands>` are left alone. | ✅ |
