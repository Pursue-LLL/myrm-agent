# api/goals/

## 架构概述

长时 Goal 编排 HTTP 层。提供单会话 Goal 操作（暂停/恢复/取消/预算/subgoal/约束/计划进度/队列）和全局跨会话 Goal 聚合接口。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Goal API exports. | [Pass] |
| `router.py` | 主路由 | Goal HTTP 聚合端点：`GET /goals/active`（某个会话的提供者抛出意外异常时跳过该会话、其余照常列出，并以 WARNING 点名它；会话在存储里的索引读不出来时，由 `GoalStorage` 点名（同一会话每 10 分钟一次），该会话按没有目标处理）、状态与生命周期操作（暂停/取消正在干活的目标时同时中断它的回合；取消作用于运行中或仍未结束的最新目标（暂停/预算受限/待复核/等待中/排队中也可取消）；恢复先有界等待被叫停的回合收尾，等不到则返回 409 且目标保持原状，等到后目标回到 active 并立即启动继续运行的无人值守回合（会话忙或应用排空时不重复启动）；等待中的目标可被暂停以取消自动唤醒；结束等待（unwait）后目标同样立即启动无人值守回合，额度上限等待中的「立即重试」则经 `usage_limit_resume.resume_goal_after_usage_limit`；状态载荷携带额度等待的恢复时间）、子路由挂载（路由器级依赖先过特性门控，再由 `require_safe_path_ids` 把关：任一路径参数（会话 id、排队目标 id、子目标序号）在白名单外的请求，含子路由的端点一律 404、不触达存储）；子目标 `text`、草拟 `objective` 与复核驳回的 `note`（客户端随后把它作为反馈发给智能体）先过风控闸门（`reject_if_risky`，命中 400 `risk_held`，目标留在待复核），再存储或交给模型 | [Pass] |
| `plan.py` | 路由与重演 | `GET /{session_id}/plan`，会话分支状态重演与工作区回退 | [Pass] |
| `schemas.py` | 模型 | 目标状态/草拟/预算/子目标端点的请求与响应体，与 `router.py` 的行为代码分开 | [Pass] |
| `queue.py` | 路由 | Goal 队列管理（查询、取消、重排）端点 | [Pass] |
| `constraints.py` | 路由 | Goal 约束管理与目标动态热编辑端点；写入前文本经 `reject_if_risky` 过风险闸门（命中返回 400 `risk_held`，原文不落库） | [Pass] |

## 关键常量

- `NON_TERMINAL_GOAL_STATUSES`: 7 种非终态状态的 frozenset，定义在 `app/services/agent/goals/goal_controls.py`，本路由与 statistics/router/activity.py 复用
