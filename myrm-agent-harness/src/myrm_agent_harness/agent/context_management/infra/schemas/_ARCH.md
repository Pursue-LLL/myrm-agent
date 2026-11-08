# context_management/infra/schemas/

## 架构概述

上下文管理的配置、模型与回调协议：按关注点分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出全部配置/模型/协议，并重导出 pre-compact 名称 | ✅ |
| `config.py` | 核心 | `ContextConfig`、默认配置与压缩阈值 | ✅ |
| `tool_protection.py` | 核心 | 工具保护配置与内置白名单 | ✅ |
| `cache.py` | 核心 | 缓存 TTL 裁剪配置与 provider 缓存反馈 | ✅ |
| `offload.py` | 核心 | offload 结果、失败分类与 eviction 类型 | ✅ |
| `summary.py` | 核心 | 紧凑工具调用、压缩意图与结构化摘要 | ✅ |
| `callbacks.py` | 核心 | 摘要持久化、offload、eviction、snapshot 协议 | ✅ |

## 依赖关系

- `callbacks.py` → `offload.py`
- `callbacks.py` → `summary.py`
