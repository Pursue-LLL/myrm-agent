# memory_guardian_guard_telemetry 模块

## 架构概述

沙箱场景下 Memory Guardian 守卫不可用标签的 Control Plane 批量遥测。本地/单机未配置 CP 时整包 no-op。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `contract.py` | 核心 | config/event dataclasses + governed label normalization | ✅ |
| `flush.py` | 核心 | envelope aggregation + Control Plane HTTP flush transport | ✅ |
| `dispatcher.py` | 核心 | 有界队列 worker + singleton start/stop/enqueue | ✅ |
| `pending_store.py` | 核心 | 未发送 envelope 落盘/重启恢复 + 文件锁 | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API | ✅ |

---

## 触发链

```
lifecycle/memory_guardian (fail-closed)
  └── enqueue_memory_guardian_guard_telemetry (dispatcher.py)
        └── Control Plane /api/telemetry/memory-guardian-guard/batch
```

---

## 依赖关系

- `app/config/settings.py` — CP telemetry 配置
- `app/schemas/control_plane.py` — batch envelope 类型
- `app/lifecycle/schedulers.py` — start/stop 委托
