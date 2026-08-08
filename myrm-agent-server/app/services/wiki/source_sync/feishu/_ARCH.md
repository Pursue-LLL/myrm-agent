# feishu/

Feishu 同步连接器子包 — 拉取编排与 Docx blocks 渲染。

## 架构概述

Feishu/Lark 域确定性同步：`__init__.py` 门面负责 channel creds + Drive folder 枚举 + Docx blocks 分页拉取 + 图片落 wiki/assets；`render.py` 为纯函数将 Docx blocks 渲染为 GFM Markdown。模块名 `app.services.wiki.source_sync.feishu`。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | Feishu channel creds + Drive folder + Docx blocks → raw/feishu/（分页全量 + 图片落 wiki/assets）+ re-export `feishu_docx_blocks_to_markdown` | ✅ |
| `render.py` | 辅助 | Feishu Docx blocks → GFM Markdown（纯函数：标题/列表/嵌套列表缩进+独立计数/代码块围栏自适应+语言/引用/待办/文件块文件名/图片占位/行内样式/行内链接+URL解码/通用元素提取覆盖新块类型/@用户/@文档/日期提醒/行内公式KaTeX/`$`转义防KaTeX误解析） | ✅ |

## 依赖

- `app.services.wiki.source_sync.schemas` — `WikiSourceSyncConfig` (POS: source sync DTOs)
- `app.services.wiki.source_sync.config_store` — UserConfig 读写 (POS: wikiSourceSync persistence)
