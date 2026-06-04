# services/files 模块架构

## 架构概述

文件内容提取服务。为 Kanban 附件、Agent 工具等非 HTTP 路径提供 bytes→text 能力，复用 Harness file_parsers，不依赖 `app/api/files` 路由层。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `content_extraction.py` | ✅ 核心 | PDF/Office 文档字节流文本提取 | ✅ |

## 依赖关系

### 内部依赖
- `myrm_agent_harness.toolkits.file_parsers`：PDF/Docx/Excel/Pptx 解析

### 被依赖方
- `app/services/kanban/task_runner.py`：任务附件上下文注入
