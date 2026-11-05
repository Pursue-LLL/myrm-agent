# cron/adapters/agent_runner/

## 架构概述

Cron 任务的 Agent 执行器：`runner.py` 编排一次执行，其余模块按执行阶段拆出（执行前检查、会话后置动作、事件流累积、profile 解析），都不持有执行器状态。包根 `__init__.py` 是唯一入口。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `__init__.py` | 门面 | 只导出 `AgentJobRunner` 与 `resolve_trusted_desktop_keys` |
| `runner.py` | 核心 | `AgentJobRunner`（JobRunner 协议实现）：每次执行时经 `load_user_configs()` 读用户最新配置，不留快照；模型优先级为绑定 Agent 的模型 > `CronJob.model` > 全局默认；经 `resolve_cron_agent_profile` 取绑定 Agent 的配置，再由 `AgentFactory` 创建 Agent；按 `SessionTarget`（ISOLATED / MAIN / DAILY）决定上下文；执行期间用 `enter_cron_execution_context()` 的 ContextVar 守卫禁止 Agent 再创建 cron 任务 |
| `support.py` | 支撑 | 执行前检查与纯辅助：内存/预算门禁、允许根、提示词构造（`_build_effective_prompt` 给周期任务追加 `[SILENT]` 指令）、每日上下文、桌面白名单解析（`resolve_trusted_desktop_keys`）、心跳跟进送达判定（`_finalize_heartbeat_follow_up_delivery`） |
| `session.py` | 辅助 | 重试退避、心跳情境报告注入、活跃目标入队 |
| `stream.py` | 辅助 | Agent 事件流消费：`_StreamAccumulator` 累加事件并构造 `JobResult`，不参与任务编排 |
| `profile.py` | 辅助 | `CronAgentProfileBootstrap` 与 `resolve_cron_agent_profile`：把绑定 Agent 的 profile 解析成执行上下文，只读，不创建任务、不写库 |

## 依赖

- 包内：`support.py` 与 `profile.py` 不引用包内其他模块；`session.py`、`stream.py` 依赖 `support.py`；`runner.py` 依赖 `session`、`profile`、`stream`、`support`
- `stream.py` 复用上级 `adapters/` 下的 `blocked_actions`、`effectful_steps`、`failure_recoverability`、`provider_window_deferral`；`runner.py` 复用 `injection_scan`、`research_lease`
