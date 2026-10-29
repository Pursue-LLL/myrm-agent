# channels/providers/feishu/sdk/

## 架构概述

飞书 SDK 封装 渠道 Provider 实现（入站/出站、凭证、路由）。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Package init for feishu SDK. Re-exports the public API surface. | ✅ |
| `_contact.py` | 模块 | Mixin that adds contact-domain API methods to FeishuClient: user info lookup by open_id. | ✅ |
| `_mentions.py` | 模块 | Defuse mention-everyone markup in text bound for a Feishu chat. `defuse_at_all()` puts a zero-width space after the `<` of `<at user_id="all">` and `<at id=all>` (any attribute ending in `id`, either quote style, spaces around `=`, any case), and also recognises the form inside message JSON where quotes are backslash-escaped; `<at user_id="ou_x">` and `all_hands` are left alone. Used by `_messaging.py` and by `documents/_cardkit.py` for streamed card text. | ✅ |
| `_messaging.py` | 模块 | Mixin that adds IM messaging, reactions, and media methods to FeishuClient. `send_message`, `reply_message`, `edit_message` and `patch_message` pass the message `content` through `defuse_at_all()` before it is posted, so a text, post or card message written by the agent never carries a live mention-everyone tag. | ✅ |
| `documents/` | 子包 | 文档域 API Mixin（Drive 元数据/媒体/目录、评论、Wiki、CardKit 流式、Docx 块与整篇 Markdown、Bitable 记录与 Base）；`FeishuDocumentsMixin` 为 FeishuClient 继承的唯一门面，详见 [documents/_ARCH.md](documents/_ARCH.md)。 | ✅ |
| `client.py` | 模块 | Standalone Feishu OpenAPI client. Usable by any module that needs Feishu API access (channels, etc.). | ✅ |
| `exceptions.py` | 模块 | Feishu-specific API error hierarchy. When used inside a channel provider, the provider is responsible for catching these and converting to the appropriate Chann | ✅ |
