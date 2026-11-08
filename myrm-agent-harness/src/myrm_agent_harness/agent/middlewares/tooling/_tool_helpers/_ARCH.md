# middlewares/tooling/_tool_helpers/

## 架构概述

工具拦截中间件的无状态助手：错误分类与校验、文本截断、超时策略、hook 结果与事件分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出全部助手 | ✅ |
| `helpers.py` | 辅助 | 错误分类、语义失败、校验、PII 与信任衰减 | ✅ |
| `truncation.py` | 核心 | 输出截断与消息文本提取 | ✅ |
| `timeouts.py` | 核心 | 按工具名推导默认超时 | ✅ |
| `hook_results.py` | 核心 | hook 失败结果构造与可观测性事件 | ✅ |

## 依赖关系

- `hook_results.py` → `truncation.py`
