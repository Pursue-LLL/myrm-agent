# memory_brief_telemetry 模块

## 架构概述

沙箱场景下 Memory Brief 状态标签的 Control Plane 批量遥测。本地/单机未配置 CP 时整包 no-op。

用户可见的 Memory Brief UI 在 `stream_session/memory_brief.py` + 前端 `MemoryInsightPanel`，与本子包无关。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `contract.py` | 核心 | Config/Event 契约 + `build_memory_brief_status_event()` | ✅ |
| `dropped_store.py` | 核心 | 背压 dropped 聚合 + 跨进程文件锁落盘/重启恢复 + 失败指数退避重试窗口 | ✅ |
| `metrics.py` | 辅助 | Prometheus Counter/Gauge（optional dependency） | ✅ |
| `flush.py` | 辅助 | Control Plane HTTP batch flush + dropped ack | ✅ |
| `dispatcher.py` | 核心 | 有界队列 worker + singleton start/stop/enqueue | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API | ✅ |

---

## 触发链

```
stream_loop / stream_finalize
  └── enqueue_memory_brief_status_telemetry (dispatcher.py)
        └── flush.py → Control Plane /api/telemetry/memory-brief-status/batch
```

---

## 依赖关系

- `app/config/settings.py` — CP telemetry 配置
- `app/schemas/control_plane.py` — batch envelope 类型
- `deployments/prometheus/rules.yml` — dropped/flush 告警
