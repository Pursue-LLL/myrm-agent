# channels/providers/matrix/

## 架构概述

Matrix 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Matrix channel provider with optional E2E encryption (E2EE). | ✅ |
| `auth.py` | 模块 | Extracted auth/init helpers for MatrixChannel. Handles aiohttp session creation (with HTTP/SOCKS proxy support), token validation via whoami, password login, in | ✅ |
| `channel.py` | 模块 | Matrix channel — mautrix SDK with optional E2EE. | ✅ |
| `crypto.py` | 模块 | E2EE initialization for Matrix channel. Sets up OlmMachine with SQLite-backed CryptoStore, handles device key verification, cross-signing bootstrap, and recover | ✅ |
| `handlers.py` | 模块 | Event handling for MatrixChannel. Processes inbound m.room.message events (text, image, audio, video, file), parses relations (reply-to, thread), identifies DMs | ✅ |
| `html.py` | 模块 | Lightweight regex-based Markdown→HTML converter for Matrix ``org.matrix.custom.html``. Supports: code blocks, inline code, bold, italic, strikethrough, links, h | ✅ |
| `media.py` | 模块 | Media handling for MatrixChannel. Uploads files, encrypts attachments in E2EE rooms, and sends m.image/m.audio/m.video/m.file events. Handles mxc:// URL pass-th | ✅ |
