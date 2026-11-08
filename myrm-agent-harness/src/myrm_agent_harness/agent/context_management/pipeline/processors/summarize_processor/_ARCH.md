# pipeline/processors/summarize_processor/

## 架构概述

结构化会话摘要：熔断状态、确定性降级、超时守卫与处理器实现各自独立，`__init__.py` 是唯一门面。上级：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `SummarizeProcessor` 与熔断/降级函数 | ✅ |
| `circuit_breaker.py` | 核心 | 连续失败计数、错误分级冷却、半开探测 | ✅ |
| `fallback.py` | 核心 | 无 LLM 的确定性摘要与压缩意图提取 | ✅ |
| `guard.py` | 核心 | 进度感知的空闲超时、总上限与取消安全清理 | ✅ |
| `apply.py` | 核心 | 受保护头部 + 摘要 + 近期尾部的消息重写 | ✅ |
| `processor.py` | 核心 | `SummarizeProcessor` 决策与编排 | ✅ |

## 依赖关系

- `processor.py` → `apply.py`
- `processor.py` → `circuit_breaker.py`
- `processor.py` → `fallback.py`
- `processor.py` → `guard.py`
