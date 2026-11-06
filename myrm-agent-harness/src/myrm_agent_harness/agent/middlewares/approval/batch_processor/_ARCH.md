# approval/batch_processor/

## 架构概述

安全审批批处理：YOLO 分支独立成 `yolo.py`，其余决策流仍在 `core.py`；`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出 evaluate / apply / interrupt / reviewer 等公开与测试依赖名 |
| `core.py` | `evaluate_tool_batch` 主决策流与自动模式判定 |
| `yolo.py` | `_evaluate_yolo_batch`、YOLO 可用性与 operator-as-key 拒绝 |

## 已知遗留

`core.py` 仍超过 400 行：主决策函数的单工具循环与安全分支深度耦合，进一步拆分需要把 700+ 行循环改成显式上下文对象，属于重写级改动；先由 `tests/agent/middlewares/approval/test_batch_processor_characterization.py` 锁定行为。
