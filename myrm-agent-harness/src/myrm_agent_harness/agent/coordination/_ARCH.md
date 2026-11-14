# coordination — Background Completion Wakeup

## 架构概述

后台任务结算之后，是否、以何种方式再次唤醒父会话的协调层。`adaptive_wakeup/` 在有界的连续唤醒预算内给出 FOLLOWUP / DEGRADE / SUPPRESS 决策。子 Agent 之间没有直连通道：每个子 Agent 的结果只汇报给父 Agent，由父 Agent 通过 `subagent_control_tool` 与完成通知统一读取。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `adaptive_wakeup/` | 核心 | 后台任务完成后的自适应唤醒路由：用户停止抑制、有界连续唤醒预算（FOLLOWUP / DEGRADE / SUPPRESS；结算只读预算，唤醒回合真正开始时由宿主 `claim_wake_turn` 扣一次）(types, budget_tracker, adaptive_router) | ✅ |
| `__init__.py` | 导出 | Public API surface | ✅ |

## 模块依赖

- `app.services.agent.wakeup_handler` & `background_job_finish_handler` — hand settlements to `adaptive_wakeup/service.py`, which decides the followup (the router only reads the budget; the wake turn spends it)
