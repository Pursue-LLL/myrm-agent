# services/memory/markdown_chunker 模块架构

## 架构概述

Markdown 滑窗切片与增量索引：`MarkdownChunkerService` 封装 Harness `MarkdownSlidingWindowChunker`、`IncrementalIndexingPipeline`（按配置指纹缓存）与 `ChunkSourceHydrator`，提供切片、增量差异索引（含 token 节省遥测）与上下文回填，DTO 来自 `app.schemas.markdown_chunker`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 导出 `MarkdownChunkerService` 与 `get_markdown_chunker_service` | ✅ |
| `provider.py` | 核心 | `MarkdownChunkerService`：slice_markdown / incremental_index / hydrate_context；`get_markdown_chunker_service` 单例入口；Harness 与 DTO 的转换辅助 | ✅ |
