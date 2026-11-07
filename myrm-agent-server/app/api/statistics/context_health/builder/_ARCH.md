# app/api/statistics/context_health/builder 子包架构

会话上下文健康度聚合的构建层。纯函数 + 冻结 dataclass，无状态、无 IO；`app.api.statistics.context_health.context_health` 保持原导入路径，内部转调本包。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `build_context_health` / `build_chat_compaction_snapshot` 与 4 个健康 DTO | — |
| `models.py` | 辅助 | `HealthStatus` 词表与状态排序、告警阈值常量、4 个冻结 dataclass（ChatCompactionSnapshot / CompactionHealth / PruningHealth / ContextHealth） | — |
| `coercion.py` | 辅助 | 防御式 int / ratio / bool / count-map 强制转换、状态取最大、restore 计数回填 | — |
| `compaction.py` | 核心 | `_build_compaction_health`：压缩快照 → 健康度 | — |
| `pruning.py` | 核心 | `_build_pruning_health`：prune 事件 → 健康度（负收益、refetch 比、restore ROI） | — |
| `build.py` | 核心 | 两个公开构建入口：`build_context_health` / `build_chat_compaction_snapshot` | — |

## 依赖方向

`models`（叶子）← `coercion` ← `compaction` / `pruning` ← `build`；单向无环。

## 说明

- 原 `context_health.py` 中的 247 行 `_build_pruning_health` 原样保留在 `pruning.py`（未做函数级重写，只解决文件过长/定位问题）；
- `context_health.py` 现在是 39 行门面：转导出构建入口、DTO 以及外部从这里取用的 `CacheHealth` / `RetentionObservationState`。
