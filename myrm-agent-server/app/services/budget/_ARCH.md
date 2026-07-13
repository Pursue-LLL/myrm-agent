# services/budget 模块架构


## 架构概述

预算治理服务层。桥接 harness 层 MultidimensionalBudgetGuard 协议与 server 侧持久化（UserConfig）和 SSE 告警，
为前端提供多维预算配置（per-session / daily / per-call）、实时花费状态、三级渐进式响应和超限/警告通知。
策略修改时保留当天已累计花费；进程重启时从 Message 表恢复当天花费，确保 block 模式持续有效。
每次新对话调用 `reset_session_budget()` 重置会话计数器。
通过 `is_eco_mode_active()` 向上下文管道提供预算压力信号（Eco 模式），预算紧张时触发更积极的上下文压缩以节省 token 成本。

### 双层预算拦截

全局预算（enforcer.py）+ 频道预算（channel_budget.py）组成双层防线：
1. **频道层**：每个 IM 渠道/群聊独立的日预算配额，防止单个群聊耗尽 Owner 全部预算
2. **全局层**：全局日预算上限，所有频道 + WebUI 共享

频道预算复用 harness 层 `DailyBudgetGuard`，零框架修改。

## 文件清单

| 文件                | 地位   | 职责                                                                                             | I/O/P |
| ------------------- | ------ | ------------------------------------------------------------------------------------------------ | ----- |
| `__init__.py`       | 入口   | 模块初始化                                                                                       | ✅    |
| `enforcer.py`       | 核心   | BudgetPolicy 模型 + MultidimensionalBudgetGuard 单例管理 + DB 读写 + SSE 告警 (warning/finalization/exceeded) + should_block_execution 执行门禁 + reset_session_budget + 花费持续性；Sandbox 模式注入 PlatformBudgetAdapter | ✅    |
| `channel_budget.py` | 核心   | ChannelBudgetPolicy + ChannelBudgetRegistry（per-channel DailyBudgetGuard 注册表）+ DB 持久化 + channel 级 SSE 告警 + should_block_channel + record_channel_cost + 审计归因查询 | ✅ |

## 依赖关系

### 输入依赖

- `myrm_agent_harness.utils.token_economics.BudgetChecker`：预算检查器协议
- `myrm_agent_harness.utils.token_economics.MultidimensionalBudgetGuard`：多维预算守卫实现
- `myrm_agent_harness.utils.token_economics.BudgetDimension`：预算维度配置
- `myrm_agent_harness.utils.token_economics.DailyBudgetGuard`：日预算守卫（channel_budget 复用）
- `app.database.models.chat.Chat, Message`：消息模型（查询当天 costUsd/channelSenderId 恢复花费和审计）
- `app.database.models.config.UserConfig`：配置持久化模型
- `app.services.event.app_event_bus`：SSE 事件总线

### 被依赖

- `app.api.budget.router`：REST API 端点（全局 + 频道 CRUD + 审计查询）
- `app.ai_agents.general_agent.factory`：Agent 构建时注入 budget_guard
- `app.services.agent.streaming`：Web 会话 + Deep Research 执行前 block 检查 + session 重置
- `app.core.channel_bridge.agent_executor.execute_preamble`：渠道入站消息执行前双层 block 检查（全局 + 频道）；频道花费记录与 sender_id 审计在 `execute_finalize` / stream 路径
- `app.services.agent.wakeup_handler`：Headless 唤醒执行前 block 检查
- `app.core.cron.adapters.agent_runner`：Cron 执行前 block 检查
- `app.server.lifespan`：启动时初始化频道预算注册表
