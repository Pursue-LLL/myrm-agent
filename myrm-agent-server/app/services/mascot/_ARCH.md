# services/mascot/

## 架构概述

桌宠 **Mascot** 业务服务：XP 事件驱动的状态映射、情绪转换、LRU 缓存清理。Companion UI 通过 SSE `mascot_xp` 等事件消费。与 `companion/` 分工见 [../_ARCH.md](../_ARCH.md) 术语表。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `status_mapper.py` | 核心 | MascotStateMapper、MascotStatus 枚举 | — |
| `cleanup_service.py` | 辅助 | MascotLRUCacheCleanupService | — |
| `__init__.py` | 入口 | 公开导出 | — |
