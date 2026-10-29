# channels/providers/slack/

## 架构概述

Slack 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Slack channel provider package. | ✅ |
| `api.py` | 模块 | Slack Web API client. Wraps HTTP calls and error handling, providing low-level API capabilities for SlackChannel. | ✅ |
| `channel.py` | 模块 | Slack Bot channel implementation with AI Agent status indicator support. Supports DM/channel/thread messages, file upload, message edit/delete/reactions (the emoji is sent as a short name, via `providers/_emoji_shortnames.py`), Socket Mode persistent connection, native AI streaming output and assistant thread status. The placeholder and every edit carry agent text that no converter has seen, so `send_placeholder` and `edit_message` escape the tokens that notify a whole audience in the complete text before the stream delta is computed. | ✅ |
| `format_converter.py` | 模块 | Markdown → Slack mrkdwn converter. Escapes special chars (&, <, >), protects Slack angle-bracket tokens (<@mention>, <#channel>, <http://...>, <!date^...>), converts Markdown links to Slack format, handles bold/strike formatting and inserts zero-width spaces at CJK formatting boundaries. Text the agent writes never notifies a whole audience: `neutralize_broadcast_mentions()` escapes `<!here>`, `<!channel>`, `<!everyone>` and `<!subteam^ID>` (with or without a `|label`) wherever they appear, code fences and link labels included, and a Markdown link whose target starts with `@`, `#` or `!` keeps only its label. | ✅ |
| `helpers.py` | 模块 | app.channels.providers.slack.helpers — Slack pure-function helpers: Block Kit builder and inbound event parsing. | ✅ |
| `context.py` | 模块 | Slack inbound context mixin. Thread-parent cache (TTL + LRU) and mention annotation for SlackChannel. | ✅ |
| `inbound.py` | 模块 | Slack inbound mixin. Events API / interactive payload parsing for SlackChannel; applies the context mixin to each message. | ✅ |
| `thread_tracker.py` | 模块 | Slack thread tracker for auto-reply functionality. | ✅ |
| `user_resolver.py` | 模块 | Slack user resolver. Calls users.info API to fetch display_name/real_name. Supports single and batch resolution with built-in LRU+TTL cache and negative result  | ✅ |
