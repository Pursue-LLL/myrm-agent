# channels/providers/email/

## 架构概述

Email 渠道 Provider（IMAP 轮询入站 + SMTP 出站）。入站解析（附件、转发邮件、HTML 转 Markdown、线程头）拆入 `inbound.py` Mixin，渠道本体只负责凭证、生命周期与收发连接。上级文档：[../_ARCH.md](../_ARCH.md)。

- **每个 IMAP / SMTP 连接都传 `ssl.create_default_context()` 与 30 秒套接字超时**（上下文每次连接现建，不缓存；IMAP 经 `_connect_imap` 一处建立）：服务器证书与主机名被校验，企业网络兼容设置决定信任什么；对不应答的服务器，连接与每次读取 30 秒后放弃，不会让轮询线程与健康检查无限阻塞。标准库在没传上下文时用不校验的默认上下文，全局策略碰不到它；`tests/architecture/test_tls_single_trust_source.py` 对 `app/` 与 `assets/`（预置技能脚本）里缺上下文关键字的 `SMTP_SSL`、`IMAP4_SSL`、`.starttls` 调用报错，关键字名是否写对（`imaplib` 要 `ssl_context=`，`smtplib` 要 `context=`）由 `tests/channels/providers/email/test_email_connections.py` 用 `autospec` 替身钉住。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Email channel provider package facade (re-exports EmailChannel for the registry's lazy loader). | ✅ |
| `channel.py` | 模块 | Email channel: credentials, lifecycle, IMAP polling and SMTP sending over certificate-verified connections (delegates MIME assembly to `outbound.py`). | ✅ |
| `inbound.py` | 模块 | Email inbound: RFC 822 message to InboundMessage conversion. Multipart bodies, HTML-to-Markdown cleaning, attachment extraction, thread headers, automated-sender filtering and forwarded-message parsing. | ✅ |
| `outbound.py` | 模块 | Email outbound: loads attachments (local files or SSRF-validated downloads, size-capped) and assembles the multipart MIME message. Attachments that cannot be loaded are returned separately so the channel reports them instead of dropping them. | ✅ |
| `forward.py` | 模块 | Forwarded email detection and structured parsing. Separates user annotation from original email content, detects Gmail/Outlook/QQ separators and MIME message/rfc822 format. | ✅ |
