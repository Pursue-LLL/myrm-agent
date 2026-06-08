# channels/providers/slack/

## 架构概述

本目录模块说明。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Slack channel provider package. | ✅ |
| `api.py` | 模块 | Slack Web API client. Wraps HTTP calls and error handling, providing low-level API capabilities for SlackChannel. """ | ✅ |
| `channel.py` | 模块 | Slack Bot channel implementation with AI Agent status indicator support. Supports DM/channel/thread messages, file upload, message edit/delete/reactions, Socket | ✅ |
| `format_converter.py` | 模块 | Markdown → Slack mrkdwn converter. Escapes special chars (&, <, >), protects Slack angle-bracket tokens (<@mention>, <#channel>, <http://...>), converts Markdow | ✅ |
| `helpers.py` | 模块 | app.channels.providers.slack.helpers — Slack pure-function helpers: Block Kit builder and inbound event parsing. """ | ✅ |
| `thread_tracker.py` | 模块 | Slack thread tracker for auto-reply functionality. """ | ✅ |
| `user_resolver.py` | 模块 | Slack user resolver. Calls users.info API to fetch display_name/real_name. Supports single and batch resolution with built-in LRU+TTL cache and negative result  | ✅ |
