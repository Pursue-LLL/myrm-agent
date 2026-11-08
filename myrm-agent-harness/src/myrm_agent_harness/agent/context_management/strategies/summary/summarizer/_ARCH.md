# context_management/strategies/summary/summarizer/

## 架构概述

结构化摘要策略：调用、守卫、生成、预算与审计分层；`__init__.py` 是唯一门面，保持原 `summarizer` 导入面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出公开与调用方依赖的摘要函数 | ✅ |
| `invocation.py` | 逻辑 | 结构化模型构造、调用、流式进度与消息前缀 | ✅ |
| `guard.py` | 逻辑 | 是否需要摘要、辅助模型上下文裁剪 | ✅ |
| `summary.py` | 逻辑 | `generate_structured_summary` 主流程 | ✅ |
| `budget.py` | 逻辑 | 预算提示与摘要长度裁剪 | ✅ |
| `audit.py` | 逻辑 | 全量/增量审计、合并质量、指标 | ✅ |

## 依赖关系

- `audit.py` → `budget.py`
- `audit.py` → `guard.py`
- `audit.py` → `invocation.py`
- `summary.py` → `audit.py`
- `summary.py` → `budget.py`
