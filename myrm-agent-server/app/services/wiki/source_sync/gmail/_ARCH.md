# gmail/

Gmail 同步连接器子包 — 拉取编排与 HTML 渲染。

## 架构概述

Gmail 域确定性同步：`__init__.py` 门面负责 Google OAuth + Gmail API 拉取 → raw/gmail/；`html_body.py` 将 Gmail HTML 正文转换为 Markdown。模块名 `app.services.wiki.source_sync.gmail`。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | Google OAuth + Gmail API → raw/gmail/ | ✅ |
| `html_body.py` | 辅助 | Gmail HTML → Markdown（`HTML2Markdown`，ignore_images） | ✅ |

## 依赖

- `app.services.wiki.source_sync.schemas` — `WikiSourceSyncConfig` (POS: source sync DTOs)
- `app.services.agent.oauth_refresher` — Gmail token refresh
