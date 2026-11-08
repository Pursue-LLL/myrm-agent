# context_management/infra/schemas/

## 架构概述

上下文管理的配置、模型与回调协议：按关注点分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出全部配置/模型/协议，并重导出 pre-compact 名称 |
| `config.py` | `ContextConfig`、默认配置与压缩阈值 |
| `tool_protection.py` | 工具保护配置与内置白名单 |
| `cache.py` | 缓存 TTL 裁剪配置与 provider 缓存反馈 |
| `offload.py` | offload 结果、失败分类与 eviction 类型 |
| `summary.py` | 紧凑工具调用、压缩意图与结构化摘要 |
| `callbacks.py` | 摘要持久化、offload、eviction、snapshot 协议 |
