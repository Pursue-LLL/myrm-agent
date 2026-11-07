# middlewares/tooling/_tool_helpers/

## 架构概述

工具拦截中间件的无状态助手：错误分类与校验、文本截断、超时策略、hook 结果与事件分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出全部助手 |
| `helpers.py` | 错误分类、语义失败、校验、PII 与信任衰减 |
| `truncation.py` | 输出截断与消息文本提取 |
| `timeouts.py` | 按工具名推导默认超时 |
| `hook_results.py` | hook 失败结果构造与可观测性事件 |
