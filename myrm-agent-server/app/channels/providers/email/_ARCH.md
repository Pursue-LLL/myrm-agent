# channels/providers/email/

## 架构概述

Email 渠道 Provider（IMAP 轮询入站 + SMTP 出站）。入站解析（附件、转发邮件、HTML 转 Markdown、线程头）拆入 `inbound.py` Mixin，渠道本体只负责凭证、生命周期与收发连接。上级文档：[../_ARCH.md](../_ARCH.md)。

- **每个 IMAP / SMTP 连接都传 `ssl.create_default_context()` 与 30 秒套接字超时**（上下文每次连接现建，不缓存；IMAP 经 `_connect_imap` 一处建立）：服务器证书与主机名被校验，企业网络兼容设置决定信任什么；对不应答的服务器，连接与每次读取 30 秒后放弃，不会让轮询线程与健康检查无限阻塞。标准库在没传上下文时用不校验的默认上下文，全局策略碰不到它；`tests/architecture/test_tls_single_trust_source.py` 对 `app/` 与 `assets/`（预置技能脚本）里缺上下文关键字的 `SMTP_SSL`、`IMAP4_SSL`、`.starttls` 调用报错，只查传了上下文，关键字名是否写对（`imaplib` 要 `ssl_context=`，`smtplib` 要 `context=`）由调用点的测试用 `autospec` 替身钉住：渠道是 `tests/channels/providers/email/test_email_connections.py`，预置邮件技能脚本是 `tests/assets/test_imap_smtp_email_script.py`（另对本机监听口做真实握手）。

- **服务器拒绝的 IMAP 命令不当成数据，被拒绝取信的邮件不丢**（`channel.py` 的 `_require_ok`、`_fetch_new_emails`）：`imaplib` 只对 BAD 抛异常，NO 作为状态返回、拒绝文本落在数据的位置。选 INBOX 与搜索被拒时抛 `imaplib.IMAP4.error`（带服务器原话），由 `reconnect_loop` 记 warning 并退避重试；单封邮件的取信被拒时记 warning 并结束本轮，高水位 `_last_uid` 停在这封之前、下一轮重新取它——跳过它会让后面的邮件把高水位推过去、这封信永久丢失。代价：服务器持续拒绝某一封时，每一轮轮询都停在它前面并记 warning，直到服务器肯给它或它被移走。预置邮件技能脚本的 `mail_client.transport.require_ok` 是同一契约的另一份实现（脚本是独立资产，不能导入 `app`）。守护用例：`tests/channels/providers/email/test_email_channel_imap_refusal.py`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Email channel provider package facade (re-exports EmailChannel for the registry's lazy loader). | ✅ |
| `channel.py` | 模块 | Email channel: credentials, lifecycle, IMAP polling and SMTP sending over certificate-verified connections (delegates MIME assembly to `outbound.py`). A refused IMAP command is an error with the server's reason; a refused fetch is retried by the next poll. | ✅ |
| `inbound.py` | 模块 | Email inbound: RFC 822 message to InboundMessage conversion. Multipart bodies, HTML-to-Markdown cleaning, attachment extraction, thread headers, automated-sender filtering and forwarded-message parsing. | ✅ |
| `outbound.py` | 模块 | Email outbound: loads attachments (local files or SSRF-validated downloads, size-capped) and assembles the multipart MIME message. Attachments that cannot be loaded are returned separately so the channel reports them instead of dropping them. | ✅ |
| `forward.py` | 模块 | Forwarded email detection and structured parsing. Separates user annotation from original email content, detects Gmail/Outlook/QQ separators and MIME message/rfc822 format. | ✅ |
