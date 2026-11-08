# agent/dynamic_workflow/tools/

## 架构概述

Dynamic Workflow 的 PTC 工具：按工具族分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出四个工具与 `WorkflowRunGuard` | ✅ |
| `spawn.py` | 核心 | 子 Agent 派生、并发守卫、验证模式与结果规范化 | ✅ |
| `notify.py` | 核心 | 工作流阶段进度通知 | ✅ |
| `human.py` | 核心 | 中途人工输入 gate | ✅ |
| `steer.py` | 核心 | 向运行中的子 Agent 注入纠正消息 | ✅ |

## 依赖关系

- 各模块无横向依赖，全部通过 `__init__.py` 聚合。
