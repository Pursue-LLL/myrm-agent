# channels/providers/wechat/

## 架构概述

微信 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | WeChat channel providers. | ✅ |
| `ilink_channel.py` | 模块 | WeChat personal account channel (iLink). Typing ticket with 540s TTL cache (monotonic clock, proactive refresh before 600s platform expiry). Voice: platform ASR text when present; otherwise SILK→WAV via optional `wechat-silk` / `collect_issues` WARNING when pilk missing. | ✅ |
| `official_channel.py` | 模块 | WeChat Official Account channel implementation. Supports passive replies, customer service messages, rich-media (news) messages, and media send/receive. | ✅ |
| `wechat_api_client.py` | 模块 | Shared Official Account API token client (messaging + drafts); token refresh; transient retry (-1/45009); locale-aware errcode hints. | ✅ |
| `draft_service.py` | 模块 | HITL draft pipeline: resolve digest/author → title/digest/HTML visible-text compliance scan before upload (high-risk block; non-blocking hits returned); inline images before thumb; draft content = body + embedded `<style>` (from formatter SSOT) + block inline styles; uploadimg + draft/add; inline failures fail-loud. | ✅ |
| `wechat_api_errors.py` | 模块 | Locale-aware WeChat API errcode hints for HITL onboarding (IP whitelist, busy, rate limit). | ✅ |
