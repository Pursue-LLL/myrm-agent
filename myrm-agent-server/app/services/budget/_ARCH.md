# services/budget 模块架构


## 架构概述

预算治理服务层。桥接 harness 层 MultidimensionalBudgetGuard 协议与 server 侧持久化（UserConfig）和 SSE 告警，
为前端提供多维预算配置（per-session / daily / per-call）、实时花费状态、三级渐进式响应和超限/警告通知。
策略修改时保留当天已累计花费；进程重启时从 Message 表恢复当天花费，确保 block 模式持续有效。
每次新对话调用 `reset_session_budget()` 重置会话计数器。
通过 `is_eco_mode_active()` 向上下文管道提供预算压力信号（Eco 模式），预算紧张时触发更积极的上下文压缩以节省 token 成本。

## 文件清单

| 文件            | 地位   | 职责                                                                                             | I/O/P |
| --------------- | ------ | ------------------------------------------------------------------------------------------------ | ----- |
| `__init__.py`   | 入口   | 模块初始化                                                                                       | ✅    |
| `enforcer.py`   | 核心   | BudgetPolicy 模型 + MultidimensionalBudgetGuard 单例管理 + DB 读写 + SSE 告警 (warning/finalization/exceeded) + should_block_execution 执行门禁 + reset_session_budget + 花费持续性；Sandbox 模式注入 PlatformBudgetAdapter | ✅    |
| `enforcer.py` | 核心 | DailyBudgetGuard 执行与 SSE budget_alert |

## 依赖关系

### 输入依赖

- `myrm_agent_harness.utils.token_economics.BudgetChecker`：预算检查器协议
- `myrm_agent_harness.utils.token_economics.MultidimensionalBudgetGuard`：多维预算守卫实现
- `myrm_agent_harness.utils.token_economics.BudgetDimension`：预算维度配置
- `app.database.models.chat.Message`：消息模型（查询当天 costUsd 恢复花费）
- `app.database.models.config.UserConfig`：配置持久化模型
- `app.api.events.event_bus`：SSE 事件总线

### 被依赖

- `app.api.budget.router`：REST API 端点
- `app.ai_agents.general_agent.factory`：Agent 构建时注入 budget_guard
- `app.services.agent.streaming`：Web 会话 + Deep Research 执行前 block 检查 + session 重置
- `app.core.channel_bridge.agent_executor.executor`：渠道入站消息执行前 block 检查（Harness `daily_budget_blocked` 回复）
- `app.services.agent.wakeup_handler`：Headless 唤醒执行前 block 检查
- `app.core.cron.adapters.agent_runner`：Cron 执行前 block 检查
