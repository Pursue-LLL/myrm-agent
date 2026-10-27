# api/goals/

## 架构概述

长时 Goal 编排 HTTP 层。提供单会话 Goal 操作（暂停/恢复/取消/预算/subgoal/约束/DAG/队列）和全局跨会话 Goal 聚合接口。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Goal API exports. | [Pass] |
| `router.py` | 主路由 | Goal HTTP 聚合端点：`GET /goals/active`、状态与生命周期操作（取消作用于运行中或仍未结束的最新目标（暂停/预算受限/待复核/等待中/排队中也可取消）；恢复在目标回到 active 后立即启动继续运行的无人值守回合（会话忙或应用排空时不重复启动）；等待中的目标可被暂停以取消自动唤醒；额度上限等待中的「立即重试」经 `usage_limit_resume.resume_goal_after_usage_limit`；状态载荷携带额度等待的恢复时间）、子路由挂载；子目标 `text`、草拟 `objective` 与复核驳回的 `note`（客户端随后把它作为反馈发给智能体）先过风控闸门（`reject_if_risky`，命中 400 `risk_held`，目标留在待复核），再存储或交给模型 | [Pass] |
| `plan.py` | 路由与重演 | `GET /{session_id}/plan` 与 `GET /{session_id}/dag`，会话分支状态重演与工作区回退 | [Pass] |
| `queue.py` | 路由 | Goal 队列管理（查询、取消、重排）端点 | [Pass] |
| `constraints.py` | 路由 | Goal 约束管理与目标动态热编辑端点；写入前文本经 `reject_if_risky` 过风险闸门（命中返回 400 `risk_held`，原文不落库） | [Pass] |

## 关键常量

- `NON_TERMINAL_GOAL_STATUSES`: 7 种非终态状态的 frozenset，定义在 `app/services/agent/goals/goal_controls.py`，本路由与 statistics/router.py 复用
