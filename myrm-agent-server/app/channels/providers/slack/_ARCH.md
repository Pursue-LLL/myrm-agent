# channels/providers/slack/

## 架构概述

Slack 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Slack channel provider package. | ✅ |
| `api.py` | 模块 | Slack Web API client. Wraps HTTP calls and error handling, providing low-level API capabilities for SlackChannel. `chat.postMessage` and `chat.update` share one error mapping (`_raise_message_error`): auth, rate-limit (with the `Retry-After` hint) and send errors are raised, so a rejected edit reaches the router, which then posts the reply as a new message. Both go through `_call_message_method`: blocks Slack refuses (`invalid_blocks`, `invalid_blocks_format`, `msg_blocks_too_long`) are dropped and the text is posted alone. The comment that introduces an uploaded file passes through `neutralize_broadcast_mentions()` like every other text that reaches Slack without the converter. | ✅ |
| `channel.py` | 模块 | Slack Bot channel implementation with AI Agent status indicator support. Supports DM/channel/thread messages, file upload, message edit/delete/reactions (the emoji is sent as a short name, via `providers/_emoji_shortnames.py`), Socket Mode persistent connection and assistant thread status. The placeholder is a posted message (`chat.postMessage`) that stage labels, previews and the final reply replace in place (`chat.update`), never an append-only Slack stream. The placeholder and every edit carry agent text that no converter has seen, so `send_placeholder` and `edit_message` escape the tokens that notify a whole audience in the complete text. A message with buttons, quick replies or menus carries its body as section blocks (`build_message_blocks`) on `send` (last part) and on `edit_placeholder_message`, because Slack shows only the blocks once a message has any. | ✅ |
| `format_converter.py` | 模块 | Markdown → Slack mrkdwn converter. Escapes special chars (&, <, >), protects Slack angle-bracket tokens (<@mention>, <#channel>, <http://...>, <!date^...>), converts Markdown links to Slack format, handles bold/strike formatting and inserts zero-width spaces at CJK formatting boundaries. Text the agent writes never notifies a whole audience: `neutralize_broadcast_mentions()` escapes `<!here>`, `<!channel>`, `<!everyone>` and `<!subteam^ID>` (with or without a `|label`) wherever they appear, code fences and link labels included, and a Markdown link whose target starts with `@`, `#` or `!` keeps only its label. | ✅ |
| `helpers.py` | 模块 | app.channels.providers.slack.helpers — Slack pure-function helpers: Block Kit builder and inbound event parsing. `build_message_blocks` puts the body in section blocks (at most 3000 characters each) above the actions block. | ✅ |
| `context.py` | 模块 | Slack inbound context mixin. Thread-parent cache (TTL + LRU) and mention annotation for SlackChannel. | ✅ |
| `inbound.py` | 模块 | Slack inbound mixin. Events API / interactive payload parsing for SlackChannel; applies the context mixin to each message. | ✅ |
| `thread_tracker.py` | 模块 | Slack thread tracker for auto-reply functionality. | ✅ |
| `user_resolver.py` | 模块 | Slack user resolver. Calls users.info API to fetch display_name/real_name. Supports single and batch resolution with built-in LRU+TTL cache and negative result  | ✅ |
