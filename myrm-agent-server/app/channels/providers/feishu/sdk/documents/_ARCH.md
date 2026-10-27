# channels/providers/feishu/sdk/documents/

## 架构概述

飞书文档域 API 按领域拆成独立 Mixin，由 `__init__.py` 的 `FeishuDocumentsMixin` 门面组合后给 `FeishuClient` 继承。上级文档：[../_ARCH.md](../_ARCH.md)。

各 Mixin 只依赖宿主 `FeishuClient` 提供的 `ensure_token` / `_get_http` / `_auth` / `_safe_json` / `api_base` / `_MEDIA_TIMEOUT`，这组契约在 `_host.py` 的 `FeishuHost` 里声明一次；宿主在自己的类体里定义真实实现，优先于这些占位声明。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 门面：`FeishuDocumentsMixin` 组合五个领域 Mixin，并导出 `DocumentContent`。 | ✅ |
| `_host.py` | 模块 | `FeishuHost`：Mixin 可调用的宿主成员声明（仅类型契约）。 | ✅ |
| `_drive.py` | 模块 | `FeishuDriveMixin`：文档元数据 `query_document_meta`、wiki 节点反查 `get_wiki_node`、媒体下载 `download_media`、Drive 目录列举 `list_drive_folder_files`。 | ✅ |
| `_comments.py` | 模块 | `FeishuCommentsMixin`：评论读取（`batch_query_comment` / `list_comments` / `list_comment_replies`）、回复、整篇评论、表情回应。 | ✅ |
| `_docx.py` | 模块 | `FeishuDocxMixin`：块列表 `get_docx_blocks`（wiki 源同步用）；块追加 `append_docx_blocks`；整篇 Markdown `get_document_content`（评论上下文用，单次请求、表格完整，错误返回飞书错误码而不抛）；`DocumentContent` 结果类型。 | ✅ |
| `_bitable.py` | 模块 | `FeishuBitableMixin`：多维表格记录读取 `get_bitable_records`（只取第一页）与批量新增 `add_bitable_records`；建 Base `create_bitable_app`；建 Base 并灌行 `create_adaptive_bitable`。 | ✅ |
| `_cardkit.py` | 模块 | `FeishuCardKitMixin`：CardKit 流式卡片创建与更新。 | ✅ |

## 约束

- `get_document_content` 走 `GET docs/v1/content`，需要应用权限 `docs:document.content:read`；失败时 `DocumentContent.code` 为响应体里的飞书错误码，响应体没有错误码时为 HTTP 状态，非飞书格式回包为 -1。网络异常不在 SDK 内吞掉，由调用方决定降级方式。
- `append_docx_blocks` 与 `_bitable.py` 的四个方法是 SDK 原语，目前没有产品调用方（智能体没有工具使用它们）；调用方接入前不能把它们当作产品能力对外宣称。

## 测试

- `tests/channels/providers/feishu/sdk/documents/` — 按领域镜像本目录：`test_drive.py`、`test_comments.py`、`test_docx.py`、`test_bitable.py`、`test_cardkit.py`；`conftest.py` 提供 `client` fixture，`support.py` 提供 `mock_response`。
