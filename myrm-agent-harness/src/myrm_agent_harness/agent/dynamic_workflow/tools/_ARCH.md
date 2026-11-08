# agent/dynamic_workflow/tools/

## 架构概述

Dynamic Workflow 的 PTC 工具：按工具族拆分，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 导出四个工具与 `WorkflowRunGuard` |
| `spawn.py` | 子 Agent 派生、并发守卫、验证模式与结果规范化 |
| `notify.py` | 工作流阶段进度通知 |
| `human.py` | 中途人工输入 gate |
| `steer.py` | 向运行中的子 Agent 注入纠正消息 |
