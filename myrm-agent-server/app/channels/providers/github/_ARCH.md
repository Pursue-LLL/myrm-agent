# channels/providers/github/

## 架构概述

GitHub Channel Provider，仅出站：把消息作为 Issue / PR 评论发出（收件人格式 `owner/repo#number`，经 REST API，个人访问令牌鉴权）。不接收 GitHub 的任何事件，因此无需公网 Ingress（`protocols/inbound_profile.py` 中为 `OUTBOUND`）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | GitHub channel provider package. | ✅ |
| `channel.py` | 模块 | GitHubChannel: outbound-only. `send()` uses `render()` multi-chunk per issue comment; the only credential is the personal access token (the base-class `from_credentials` builds the channel from it). | ✅ |
| `helpers.py` | 模块 | Minimal GitHub REST API client: `post_issue_comment` raises `ChannelSendError` unless GitHub accepted the comment. | ✅ |
