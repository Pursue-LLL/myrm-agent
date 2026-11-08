# utils/context_format/

## 架构概述

文档与上下文的格式化：收集（按 URL 去重、生成来源标签）、token 预算控制、拼接三个阶段，另含工具结果的安全边界包装。来源标签里的编号由调用方传入的编号函数 `index_for` 给出（运行中是 `SourceTracker.index_for`：模型读到的编号就是来源卡片的编号；不传则每次调用从 1 开始）。`__init__.py` 是唯一入口。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出 `format_document_header`、`format_documents_with_metadata`、`TruncationStats`、`wrap_with_external_sources_tag`、`wrap_with_tool_output_tag` |
| `collection.py` | 收集阶段：`format_document_header`（`【序号】 URL: … \| Title: … \| Date: …`）、`DocumentCollection`、`collect_and_deduplicate_urls`（每个唯一 URL 一个来源条目、一个标签、一份聚合内容；标签的编号是 `index_for(条目)`，条目此时已完整，编号函数据此认出稍后交给追踪器的同一个来源） |
| `budget.py` | token 预算阶段：`TruncationStats`、`estimate_token_overhead`（按首个 header 的 token 数分 25/40/70 三档估算）、`allocate_tokens_weighted`（前三个文档 25%/15%/10%，其余平分）、`truncate_documents_to_fit_budget`（预算严重不足时只保留放得下的前几个文档）、`apply_token_truncation`（句子边界截断） |
| `formatter.py` | 入口 `format_documents_with_metadata`：编排收集、预算控制、拼接；预算裁掉的文档占用的编号不回收 |
| `boundary.py` | `wrap_with_external_sources_tag`（UNTRUSTED_DATA 边界 + 引用提示）、`wrap_with_tool_output_tag`（TOOL_OUTPUT 边界，不带引用提示） |
