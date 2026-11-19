# approval/batch_processor/

## 架构概述

安全审批批处理：`core.py` 组装上下文并收尾，逐工具判定循环按阶段拆在 `decide/` 子包，YOLO 分支独立成 `yolo.py`；`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出 evaluate / apply / interrupt / reviewer 等公开与测试依赖名 | ✅ |
| `_workspace_snapshot.py` | 辅助 | `pre_destructive_snapshot_id`：破坏性命令等待审批前对工作目录做快照并返回快照 id，决策循环与 YOLO 分支共用 | ✅ |
| `core.py` | 核心 | `evaluate_tool_batch` 入口、上下文组装与自动模式判定；定时运行（含其委派的子智能体）没有人能批，不走 YOLO 分支：一般分支放行的调用交给 `_cron_settle.veto_never_classes` 复核（落入四类的改为拒绝），仍挂起的调用交给 `_cron_settle` 按作业声明裁决，返回的挂起列表恒为空 | ✅ |
| `decide/` | 核心 | 逐工具判定循环的子包：预检、策略、allowlist、ALLOW 复核、污点、HITL 分类、审批卡上下文各为一个阶段模块；定时运行里本分支产生的 ASK 由 `_cron_settle.settle_ask` 就地裁决；定时运行的 auto-mode 不因拒绝累积而暂停。详见 [decide/_ARCH.md](decide/_ARCH.md) | ✅ |
| `yolo.py` | 核心 | `_evaluate_yolo_batch`（资金、社交不可逆、破坏性与受保护写入（指令文件、git 钩子与配置）调用仍挂起等人审批；只服务有人在场的运行，定时运行不进入这个分支）、YOLO 可用性与 operator-as-key 拒绝 | ✅ |

## 依赖关系

- `core.py` → `decide/`
- `core.py` → `yolo.py`
- `decide/preflight.py` → `yolo.py`
- `decide/allow_gates.py`、`decide/pending.py` → `_workspace_snapshot.py`
- `yolo.py` → `_workspace_snapshot.py`
