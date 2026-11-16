# approval/batch_processor/

## 架构概述

安全审批批处理：YOLO 分支独立成 `yolo.py`，其余决策流仍在 `core.py`；`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 evaluate / apply / interrupt / reviewer 等公开与测试依赖名 | ✅ |
| `_workspace_snapshot.py` | 辅助 | `pre_destructive_snapshot_id`：破坏性命令等待审批前对工作目录做快照并返回快照 id，决策循环与 YOLO 分支共用 | ✅ |
| `core.py` | 核心 | `evaluate_tool_batch` 入口、上下文组装与自动模式判定 | ✅ |
| `decide.py` | 核心 | 逐工具判定循环（预检、策略、allowlist、HITL 分类） | ✅ |
| `yolo.py` | 核心 | `_evaluate_yolo_batch`（资金、社交不可逆、破坏性调用仍挂起等人审批；cron 会话里没有人能批，付款类调用改为直接拒绝并记 `CRON_DENY`）、YOLO 可用性与 operator-as-key 拒绝 | ✅ |

## 已知遗留

`decide.py` 仍约 950 行：单工具循环的各安全分支共享顺序、拒绝计数与 `record_decision` 语义，再往下拆需要按阶段引入显式判定结果对象；当前由 3939 条 approval/security 测试与 characterization 用例锁定行为。

## 依赖关系

- `core.py` → `decide.py`
- `core.py` → `yolo.py`
- `decide.py` → `yolo.py`
- `decide.py` → `_workspace_snapshot.py`
- `yolo.py` → `_workspace_snapshot.py`
