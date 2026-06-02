# api/events 模块架构


---

## 架构概述

Agent 事件接口（仅本地模式）。提供 Agent 运行时事件流、权限审批和策略管理。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `router.py` | ✅ 核心 | Agent 事件流接口（Turn/Event 查询） |
| `permissions.py` | ✅ 核心 | 权限管理接口（审批、模式切换、白名单、审计日志） |
| ~~`event_bus.py`~~ | 已迁移 | → `app/services/event/app_event_bus.py`（进程内 EventBus: fan-out pub/sub, topic 订阅, backlog 回放, 事件去重, AppEvent/AppEventType 定义）|
| `notifications.py` | ✅ 核心 | SSE 端点 `/events/notifications/stream`，实时推送系统通知 |

### 支持的事件类型 (AppEventType)

| 事件类型 | 说明 | 数据字段 | IM 推送 |
|---------|------|---------|---------|
| `PAIRING_PENDING` | Channel配对请求待审批 | `channel`, `sender_id`, `display_name` | ✅ |
| `APPROVAL_REQUIRED` | 操作需要用户审批 | `approval_id`, `action_type`, `status`, `severity` | ✅ |
| `HEALTH_ALERT` | 健康检查告警 | `component`, `status`, `message`, `detail`, `fix_suggestion`, `layer` | ✅ |
| `BUDGET_ALERT` | 预算用量警报 | `subtype`, `status`, `today_cost`, `daily_limit`, `remaining`, `pct` | ✅ |
| `NEW_SKILL_DRAFT` | 草稿箱新技能 | `draft_id`, `draft_type`, `name` | ✅ |
| `MESSAGE_DEAD_LETTERED` | 消息投递永久失败 | `channel`, `error_reason` | ✅ |
| `CHANNEL_DISCONNECTED` | Channel断开连接 | `channel`, `status` | ✅ |
| `WECHAT_SESSION_EXPIRED` | 微信会话过期 | (reserved) | ✅ |
| `CONFIG_HEALTH_WARNING` | 配置健康问题警告 | `user_id`, `missing_items`, `suggestions`, `checked_at` | ✅ |
| `SYSTEM_NOTIFICATION` | 系统通知 | `title`, `message`, `type`, `meta_data` | ✅ |
| `CHANNEL_CONNECTED` | Channel连接成功 | `channel`, `status` | - |
| `GROUPS_UPDATED` | 群组列表更新 | `channel`, `count` | - |
| `SKILL_INSTALL_PROGRESS` | Skill安装进度 | `skill_id`, `stage`, `message` | - |
| `AGENT_CONFIG_UPDATED` | 智能体配置变更 | `agent_id`, `action` | - |
| `SKILL_GROWTH_UPDATED` | 技能成长案例状态变化 | `case_id`, `draft_type`, `status`, `name` | - |
| `SKILL_EVOLVED` | 技能进化完毕 | `skill_name`, `evolution_type`, `description` | - |
| `IDLE_STATUS` | 闲置状态与后台任务进度（呼吸灯） | `session_id`, `status`, `task_name`, `progress_pct`, `message`, `data` | - |
| `STATUS` | 内部状态事件（审批恢复等） | varies | - |
| `ASYNC_AGENT_STREAM_CHUNK` | 异步 Agent 流块（Idle Wakeup 唤醒后台执行） | `session_id`, `chunk` | - |
| `MEMORY_HISTORY_UPDATED` | 内存使用历史监控数据更新 | `history` | - |
| `MEMORY_OPERATION` | 记忆操作实时流（Command Center Live） | timeline event payload | - |
| `SUBAGENTS_UPDATED` | 子智能体运行状态树更新 | 无 | - |
| `APPROVAL_RESOLVED` | 审批被处理解决的信号（前端据此自动从待审队列移除） | `action`, `approval_id`, `thread_id`, `chat_id`, `agent_id`, `decision`, `edited_payload` | - |
| `CRON_UPDATED` | 计划任务执行状态或记录更新 | `id`, `text`, `level`, `job_name` | - |
| `SKILL_AB_TEST_UPDATED` | 技能 A/B 测试运行进度/结果更新 | 无 | - |
| `HEALTH_STATUS_UPDATED` | 系统整体健康分数和状态更新 | `overall_score`, `overall_status` | - |
| `BUDGET_UPDATED` | 预算或配额度量更新 | 无 | - |
| `CHANNEL_STATUS_UPDATED` | 渠道连接或错误状态更新 | 无 | - |
| `SKILL_QUALITY_UPDATED` | 技能质量评分趋势更新 | 无 | - |
| `KANBAN_TASK_UPDATED` | Kanban 任务状态变更（创建/移动/删除/依赖/评论/晋升等） | `board_id`, `task_id`, `action` | ✅ (terminal only) |
| `GOAL_TERMINAL` | Goal 达到终态（complete/cancelled/budget_limited/needs_human_review） | `goal_id`, `session_id`, `status`, `objective`, `files_modified`, `total_tokens`, `total_cost_usd` | ✅ |
| `UX_WARNING_TRUNCATED` | 前端截断警告事件（DOM/多模态超大输入时触发保护截断） | `message` | - |

### permissions.py 功能

**权限审批**：
- `POST /pending/{request_id}/approve` - 审批权限请求
  - 支持 `always_allow` 标志，永久保存允许规则到数据库白名单
  - 使用 `LOCAL_USER_ID` 作为本地模式用户标识
  - 完整错误处理和审计日志
- `GET /pending` - 获取所有待审批请求
- `GET /pending/{request_id}` - 获取单个待审批请求

**白名单管理**：
- `GET /allowlist` - 查询用户的永久允许规则
- `DELETE /allowlist/{permission}` - 删除特定规则

**安全模式**：
- `GET /mode` - 获取当前安全模式（safe/ask/allow_all）
- `POST /mode` - 切换安全模式
  - 持久化到 `~/.myrm/permission_mode.txt`
  - 动态构建 `SecurityConfig` (框架层)

**权限检查**：
- `POST /check` - 执行权限检查
  - 使用框架层 `evaluate_tool_call` 
  - Fail-closed 策略：评估失败时拒绝
  - 结构化审计日志记录

---

## 依赖关系

**框架层**：
- `myrm_agent_harness.agent.security.engine.evaluate_tool_call` - 权限评估
- `myrm_agent_harness.agent.security.types` - SecurityConfig, PermissionAction, PermissionRule
- `myrm_agent_harness.agent.security.approval_flow` - Allowlist, AllowlistEntry

**业务层**：
- `app/api/dependencies.py` - 数据库会话、本地模式守卫
- `app/config/deploy_mode.py` - 部署模式判断
- `app/database/allowlist_store.py` - 白名单持久化（DBAllowlistStore）
- `app/core/channel_bridge/pairing_store.py` - 发布 `PAIRING_PENDING` 事件
