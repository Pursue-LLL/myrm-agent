# app/services/agent/params/mention 子包架构

`@` 引用子域。把 GUI 传来的结构化引用（以及历史纯文本 `@` 形式）展开成一段注入用户消息的 XML 上下文。

调度顺序与 token/byte 预算只由 `pipeline.py` 持有；各类引用的读取实现放在 `references/`，每个 `ref.type` 一个模块，互不编排。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合导出公开 API（`_build_mention_reference_context`、`_inject_mentioned_files_into_query` 等）与既有测试使用的内部函数 | — |
| `pipeline.py` | 核心 | 调度 `HANDLERS`、累计字节、25%/50% token 预算与告警、组装 `<mentioned_files>`；`_inject_mentioned_files_into_query()` 把上下文追加到 query | ✅ |
| `context.py` | 辅助 | `MentionContext`：一次展开的可变累加状态（workspace、agent、fragments、已用字节、告警） | — |
| `xml.py` | 辅助 | `<mentioned_file>` 三种片段形态、大小格式化、内联预算判定与 `100KB/500KB` 常量 | ✅ |
| `documents.py` | 辅助 | Office/PDF 解析与文档/二进制扩展名分类（工作区文件与存储上传共用） | ✅ |
| `text_references.py` | 辅助 | 纯文本 `@` 适配：`@file.py:10-20`、`@staged`、`@diff`、`@codebase`、`@folder:`、`@url:` → 结构化引用 | ✅ |
| `references/` | 子包 | 每类引用一个处理器，聚合出口见 `references/_ARCH.md` | ✅ |

## 依赖关系

- 上游：`params/models.py`（`MentionReferenceRequest` / `MultimodalQuery`）、`params/enrichment/pipeline.py`（调用方）
- 下游：harness 路径安全 / 文档解析 / `FetchEngine` / `WikiStructure`、`app.core.storage`（上传）、`app.services.chat`（历史会话召回）
