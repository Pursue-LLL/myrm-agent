# workflow/

## 架构概述

工作流执行轨迹与断点重放的服务层。轨迹存在进程内存里，初始化时预置示例工作流；从指定节点重放时改写已存的节点快照并把其后的节点标记为刷新，不运行智能体。HTTP 入口在 [../../api/workflow/](../../api/workflow/_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包标识 | — |
| `trace_service.py` | 核心 | `WorkflowTraceService`：`get_workflow_trace` 取已存轨迹；`replay_from_node` 以合并后的输入重写目标节点、刷新其后的节点并回存；`get_workflow_trace_service` 提供进程内单例 | ✅ |

## 边界

- 依赖 `app/schemas/workflow_trace.py` 的轨迹、节点快照与重放请求 / 响应类型。
- 轨迹不落库，进程重启后回到预置的示例工作流。

## 测试

- `tests/api/workflow/test_trace_api.py` — 读取预置示例工作流轨迹、按需读取、从节点重放成功、节点不存在
