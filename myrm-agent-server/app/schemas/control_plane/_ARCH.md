# app/schemas/control_plane 子包架构

Server ↔ Control Plane 的遥测契约。按数据族分模块，`__init__.py` 聚合全部公开模型。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 15 个模型（上下文快照、遥测信封） | — |
| `context_events.py` | 核心 | 上下文压缩 / 重取 / 归档恢复的事件快照 | ✅ |
| `context_snapshot.py` | 核心 | 完整的上下文压缩快照负载 | ✅ |
| `coercion.py` | 辅助 | 防御性类型转换 helper（int / float / str / list / count map 等），被快照模型共用 | ✅ |
| `telemetry.py` | 核心 | 上下文压缩遥测信封与批负载、Memory Brief 状态聚合/信封、Memory Guardian 守卫聚合/信封 | ✅ |

## 依赖关系

- 上游：`pydantic`
- 下游：`app/services/agent/context_compaction_telemetry.py`、`app/services/agent/memory_brief_telemetry/`、`app/services/agent/memory_guardian_guard_telemetry/`
