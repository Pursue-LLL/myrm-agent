# channels/providers/feishu/comment/

## 架构概述

飞书云文档评论回合：评论事件转成一轮对话，回复按评论位置送回，并为这一轮读取所评文档的正文。上级文档：[../_ARCH.md](../_ARCH.md)。

数据流：`drive.notice.comment_add_v1` 事件 → `CommentHandler` 转成 `InboundMessage`，`chat_id` 编码为 `comment-doc:{file_type}:{file_token}:{comment_id}:{is_whole}` → 路由器在回合开始时调用 `FeishuInboundMixin.read_context_document`，由 `read_comment_document` 取文档正文 → 智能体回复的 `recipient_id` 仍是这个编码，`FeishuOutboundMixin._send_comment_reply` 解析后由 `deliver_comment_reply` 分块发回评论。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 门面：导出 `CommentHandler`、`CommentRouteInfo`、路由编码与解析、`deliver_comment_reply`、`NO_REPLY_SENTINEL`、`read_comment_document`；入站与出站 Mixin 只从这里导入。 | ✅ |
| `content.py` | 模块 | 评论内容提取与提示词构造：纯函数，除 wiki 链接解析需要 `FeishuClient` 外没有 I/O；只被 `handler.py` 使用。 | ✅ |
| `document.py` | 模块 | `read_comment_document()`：所评 docx 的 Markdown 正文（`FeishuClient.get_document_content`，权限 `docs:document.content:read`），返回 `ContextDocument`；非 docx 不调接口直接记为 UNSUPPORTED；无权限、过大、其它失败各映射成状态；15 秒超时；不抛出（评论回复无论是否读到正文都必须发出）。 | ✅ |
| `handler.py` | 模块 | 评论事件处理：事件转 `InboundMessage`、`comment-doc:` 路由编码与解析、回复分块投递；`NO_REPLY_SENTINEL` 表示智能体有意不回复。 | ✅ |

## 测试

- `tests/channels/providers/feishu/comment/` — `test_handler.py`（路由编码、分块回复、事件模型、提示词构造、渠道与 webhook 路由、`content.py` 的提取函数）、`test_document.py`（文档读取与状态映射）。
