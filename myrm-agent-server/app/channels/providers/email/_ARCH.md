# channels/providers/email/

## 架构概述

Email 渠道 Provider（IMAP 轮询入站 + SMTP 出站）。入站解析（附件、转发邮件、HTML 转 Markdown、线程头）拆入 `inbound.py` Mixin，渠道本体只负责凭证、生命周期与收发连接。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Email channel provider package facade (re-exports EmailChannel for the registry's lazy loader). | ✅ |
| `channel.py` | 模块 | Email channel: credentials, lifecycle, IMAP polling and SMTP sending (delegates MIME assembly to `outbound.py`). | ✅ |
| `inbound.py` | 模块 | Email inbound: RFC 822 message to InboundMessage conversion. Multipart bodies, HTML-to-Markdown cleaning, attachment extraction, thread headers, automated-sender filtering and forwarded-message parsing. | ✅ |
| `outbound.py` | 模块 | Email outbound: loads attachments (local files or SSRF-validated downloads, size-capped) and assembles the multipart MIME message. Attachments that cannot be loaded are returned separately so the channel reports them instead of dropping them. | ✅ |
| `forward.py` | 模块 | Forwarded email detection and structured parsing. Separates user annotation from original email content, detects Gmail/Outlook/QQ separators and MIME message/rfc822 format. | ✅ |
