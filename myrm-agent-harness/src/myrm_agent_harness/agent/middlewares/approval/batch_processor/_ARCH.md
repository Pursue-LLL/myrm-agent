# approval/batch_processor/

## 架构概述

安全审批批处理：YOLO 分支独立成 `yolo.py`，其余决策流仍在 `core.py`；`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出 evaluate / apply / interrupt / reviewer 等公开与测试依赖名 |
| `core.py` | `evaluate_tool_batch` 入口、上下文组装与自动模式判定 |
| `decide.py` | 逐工具判定循环（预检、策略、allowlist、HITL 分类） |
| `yolo.py` | `_evaluate_yolo_batch`、YOLO 可用性与 operator-as-key 拒绝 |

## 已知遗留

`decide.py` 仍约 930 行：单工具循环的各安全分支共享顺序、拒绝计数与 `record_decision` 语义，再往下拆需要按阶段引入显式判定结果对象；当前由 3939 条 approval/security 测试与 characterization 用例锁定行为。
