# feishu/

## 架构概述

Feishu/Lark 文档确定性同步子包：门面连接器 + 纯函数 Markdown 渲染器，零 LLM。组织与 `gmail/` 子包对齐：`feishu.py` 为域门面（连接 + re-export），渲染器无 I/O 无状态。

上级文档：[../_ARCH.md](../_ARCH.md)

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | re-export `sync_feishu_docs_to_wiki` / `feishu_docx_blocks_to_markdown` / `is_feishu_wiki_sync_available`（消费者唯一入口） | ✅ |
| `feishu.py` | 核心 | Feishu channel creds + Drive folder + Docx blocks → raw/feishu/（分页全量 + 图片落 wiki/assets） | ✅ |
| `feishu_render.py` | 辅助 | Feishu Docx blocks → GFM Markdown（纯函数：标题/列表/嵌套列表缩进+独立计数/代码块围栏自适应+语言/引用/待办/文件块文件名/图片占位/行内样式/行内链接+URL解码/通用元素提取覆盖新块类型/@用户/@文档/日期提醒/行内公式KaTeX/`$`转义防KaTeX误解析） | ✅ |
| `feishu_render_inline.py` | 辅助 | 行内元素渲染（链接/样式/公式/URL 解码等 Docx 行内块 → Markdown 内联） | ✅ |

## 测试

- `tests/services/wiki/test_feishu_source_sync.py` — Docx blocks 全量渲染 + 同步编排（经门面引用，不经内部路径）
- `tests/services/wiki/test_feishu_images.py` — 图片下载→wiki/assets 落盘 + 失败降级

## 依赖

- `app.services.wiki.source_sync.publish_helpers` — publish_raw 统一发布
- `app.services.wiki.source_sync.schemas` — run result DTO
- `app.channels.providers.feishu.sdk.client` — Feishu OpenAPI client
- `myrm_agent_harness.toolkits.wiki` — WikiStructure / asset store