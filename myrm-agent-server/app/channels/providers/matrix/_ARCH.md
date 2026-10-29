# channels/providers/matrix/

## 架构概述

Matrix 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Matrix channel provider with optional E2E encryption (E2EE). | ✅ |
| `auth.py` | 模块 | Extracted auth/init helpers for MatrixChannel. Handles aiohttp session creation (with HTTP/SOCKS proxy support), token validation via whoami, password login, in | ✅ |
| `channel.py` | 模块 | Matrix channel — mautrix SDK with optional E2EE: lifecycle entry points and outbound (text and edit sends share `_post_message`, which bounds the wait on the homeserver; a text send lists the members it addresses, never the bot itself, in `m.mentions`, an edit sends an empty one); composes `MatrixConnectionMixin`; diagnosis is delegated to `diagnostics.py`. A reaction is an annotation event whose id is remembered so an empty emoji redacts it; failures propagate to the reaction funnel. | ✅ |
| `connection.py` | 模块 | `MatrixConnectionMixin`: mautrix client setup, authentication, E2EE initialisation and cleanup, and the room-message / invite / reaction event wrappers. | ✅ |
| `crypto.py` | 模块 | E2EE initialization for Matrix channel. Sets up OlmMachine with SQLite-backed CryptoStore, handles device key verification, cross-signing bootstrap, and recover | ✅ |
| `diagnostics.py` | 模块 | `collect_matrix_issues`: pure diagnosis of the Matrix configuration, optional dependencies and login state for `MatrixChannel.collect_issues`; never touches the network. | ✅ |
| `handlers.py` | 模块 | Event handling for MatrixChannel. Processes inbound m.room.message events (text, image, audio, video, file), parses relations (reply-to, thread), identifies DMs | ✅ |
| `html.py` | 模块 | Markdown→`org.matrix.custom.html` 的正则转换（代码块、行内代码、粗体、斜体、删除线、链接、标题、列表、引用）；整词的 `@name` 转成房间成员的完整 Matrix ID（代码块内不转；邮箱地址与带点的主机名里的 @ 不算，已写成完整 ID 的保持原样），`mentioned_user_ids` 给出被点名的成员（按名字或按完整 ID），文本事件的 `m.mentions` 只写这些成员的 `user_ids`（没有就是空对象，从不 @room），编辑与媒体事件的 `m.mentions` 一律为空对象。 | ✅ |
| `media.py` | 模块 | MatrixChannel 的媒体收发：上传文件，E2EE 房间加密附件，发送 m.image/m.audio/m.video/m.file 事件，`mxc://` 链接直接转发；每个事件的 `m.mentions` 为空对象，文件名里的 @name 不会 @ 到人。 | ✅ |
