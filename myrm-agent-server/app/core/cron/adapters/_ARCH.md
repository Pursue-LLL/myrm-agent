# core/cron/adapters 模块架构


---

## 架构概述

Cron 定时任务系统的业务层适配器。将框架层的 CronStore / JobRunner / ResultDelivery 协议映射到应用层的具体实现（SQLAlchemy、Agent 管道、Channel Gateway）。`setup.py` 是唯一的组装入口。

在 Agent-in-Sandbox 架构下，每个沙箱是单 Worker，CronScheduler 不使用分布式锁。

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `setup.py` | 组装入口：创建 CronScheduler + entitlement-guarded CronManager，注入所有适配器 |
| `entitlement_guarded_manager.py` | 包装 harness CronManager：`create_job` / `duplicate_job` 先占用套餐名额（`require_cron_slot`）；`create_job` / `update_job` 再过 `lifecycle_guard` 并用 `tools_policy.normalize_cron_tools_allowed` 规范化工具名；`create_job` 透传 harness 全部字段（`project_id` / `skill_ids` / `workflow_template_id` / `workflow_template_args` 等，签名漂移由 `test_create_job_forwards_every_harness_field` 守住）；`update_job` 先把库里的 prompt / command / pre_condition_script / 验收标准与补丁合并（`clear_*` 视为已清空）再过守卫；`get_job` / `list_jobs` / `list_runs` / `pause_job` / `resume_job` / `delete_job` / `trigger_now` 为带类型的直通方法 |
| `lifecycle_guard.py` | 拦截 cron prompt / command / pre_condition_script 与 shell 类验收标准的 `command` 中停止或重启 Myrm 服务的命令（防自杀 cron）：`myrm` / `myrm-dev` 的 restart/stop、launchctl 与 systemctl 的启停、按名终止 `myrm-agent*` 进程（`pkill` / `kill` / `killall` / `taskkill` / `Stop-Process`）；动词与服务名须在同一行内相距不超过 200 个字符（间隙无上界会让重复动词的长文本扫描变成平方级）；单词内的 `kill`（如 skill）不算命令；语义类验收标准与 `workflow_template_args` 不扫 |
| `tools_policy.py` | ``tools_allowed`` 规范化（保留 baseline 工具 ID）+ runtime 求交（含 memory 白名单剔除）+ ``resolve_cron_runtime_tool_flags``（受限 job 不强制 baseline，`enable_memory` 由 runner 按「白名单 ∩ 用户全局 enableMemory」双门控判定，与 web_search 白名单语义一致） |
| `sqlalchemy_store.py` | CronStore 协议的 SQLAlchemy 实现：Job/Run/MonitorState CRUD（`save_job`、`save_monitor_state` 是读后写，起手 `acquire_write_lock`（写锁策略见 `app/database/_ARCH.md`）：被认领的任务只靠 `save_job` 的写回恢复 `next_run_at`，监控任务的新基线只靠 `save_monitor_state` 存下，读写之间若有别的写者提交，SQLITE_BUSY_SNAPSHOT 会丢掉写入——任务从此不再触发，或这一轮被执行器算作监控失败、基线没存；其余写方法写在先或纯读，不需要。`get_job` 路径对 legacy monitor_config 做 opportunistic 回写清洗（一次性迁移，不为它给每次读加写锁），列表读取仅规范化映射不触发写入；启动阶段支持批量清洗并可设置批次数上限保护冷启动时延，返回结构化清洗统计与续清标记供可观测性收口） |
| `sqlalchemy_mapping.py` | ORM <-> Domain 双向映射（含 monitor_config 规范化）；更新路径 `apply_job_to_model`、创建路径 `job_to_model`、读取路径 `job_to_domain` 各自维护一份字段清单，每条路径都要覆盖 `CronJobModel` 的每一列（更新不碰 `id`、`created_at`，创建不传 `created_at`、`updated_at`），`CronJob` 的每个字段必须有同名的列，或列在测试的不落库名单里（`user_id` 读回固定为单用户 `default`）；由 `tests/core/cron/adapters/test_sqlalchemy_mapping.py` 的列覆盖测试、字段→列测试与真实 SQLite 往返测试守住：新增列漏掉任一路径、新增字段没有列且不在名单里，都会红 |
| `sqlalchemy_aggregation.py` | Token 用量聚合查询 |
| `python_condition.py` | PreFlightCondition 协议实现：SandboxedPythonCondition 在沙箱内安全执行前置探针脚本 |
| `provider_window_deferral.py` | `usage_limit_deferral(exc)`：agent 运行因提供方额度窗口失败且边界可等待（≤24h，经 harness `deferral_wait_s`）时返回带 `retry_at` 的 `JobResult`（`skip_reason=usage_limit`），executor 将任务保持 ACTIVE 并在重置时刻重跑、不计失败；`agent_runner._failure_result` 调用，`run()` 对带 `retry_at` 的结果不做进程内重试；ONCE 任务遇内存过载跳过同样经 `retry_at` 重排，避免被消费 |
| `agent_runner.py` | JobRunner 协议实现：通过 Agent 管道执行 cron 任务（输出文本经 `AnswerDraft` 累积，恢复重放只丢在途段落）；**运行时再判允许根**：`_resolve_effective_allowed_roots` 取任务自己的 `allowed_roots`（没有则用所属项目的工作区），再经 `require_grantable_roots` 复判，含受保护位置的根使本次运行失败（`WorkspacePathValidationError`），不把过宽的根交给沙箱当可写范围，写入口已拒绝这类值，这里兜住没经过写入口的值（导入实例、直接写库）；`run()` 全程经 `core.agent.run_activity.track_background_agent_run` 计入 liveness `busy`（云托管空闲回收器据此不在任务中途暂停沙箱）。始终以 `unattended_mode=True` 运行（跳过 ask_question_tool 工具注册 + 注入无人值守系统提示词），防止定时任务被 HITL 交互阻塞。当 `workflow_template_id` 绑定时，启动 DW stream 前调用 `workflow_templates/validation.validate_cron_template_at_execution`（trust_latch + args + readonly spawn 复检）。当 CronJob.agent_id 存在时，通过 AgentProfileResolver 加载完整配置（含 `enabled_builtin_tools`、`auto_restore_domains`、`memory_decay_profile`、`cron_post_run_verify`），team protocol 与 **`profile_output_suffixes`**（人格 + `response_locale_policy`）注入 `user_instructions` 尾，并通过 `resolve_builtin_tool_flags()` 统一映射 builtin 工具 flag，解析 agent/cron/chat 绑定的 Shared Context 注入 `memory_shared_context_ids`。**`enable_memory` 双门控（`_resolve_cron_enable_memory`）：intersect 后工具集含 memory（`tools_allowed` 白名单）AND 用户全局 `enableMemory` 开启（与 channel/voice 一致）**，任一不满足即禁挂 memory 工具组，防止受限/用户关闭记忆的任务自动写长期记忆。**桌面无人值守信任闩**：profile `trusted_desktop_apps`（`{name, app_id?}`）经 `resolve_trust_key` 解析为信任键后注入 `GeneralAgentParams.desktop_preapproved_trust_keys`，并置 `desktop_unattended_fail_fast=True`——预信任应用秒过门禁，其余秒级拒否（不等 60 秒），失败走既有 failure webhook 非无声阻塞。**Post-run delivery verification**：Agent 流结束后、可选调用 `post_run_verification.apply_cron_post_run_verification()`（verifier-only，120s 超时；FAIL 不改变 run success，写入 `metadata.verification`）。**Thread Automation**：当 `session_target=MAIN` 且 `chat_id` 存在时，通过 `_load_thread_history` 加载目标会话的 compacted_summary + 近 30 条消息作为 `chat_history` 注入 Agent，实现定时任务的上下文连续性。**Heartbeat follow-up ack**：heartbeat 运行结束后调用 `_finalize_heartbeat_follow_up_delivery()`，按 `[SILENT]` 判定 SENT 或 snooze，并顺带跑一次群停滞懒扫描（覆盖全静默群）。**只读租约**：声明能力全为只读（含无声明）的作业，运行挂 `research_lease` 的只读租约，工具调用时由审批中间件默认拒绝租约外工具。**非所有者触发**：事件作业由非所有者的消息拉起时（`is_untrusted_ingress_active()` 由 `inbound_event_dispatch` 的围栏作用域带入调度器任务），运行强制挂租约、`enable_memory` 恒为假（不读写所有者记忆，`_resolve_cron_enable_memory(untrusted=)`）、不加载 MAIN 会话历史、不入队为目标（否则其文本会在所有者会话里脱离围栏执行），工作流模板作业直接跳过（`skip_reason=untrusted-workflow`）；其余触发来源（定时、手动、REST、webhook、系统事件）不经此围栏；**重试安全**：`_StreamAccumulator.effectful`（已记录的步骤里有改变状态的工具调用，判定见 `effectful_steps.py`；工作流任务：任一步骤开始）决定 `to_result`、`_failure_result` 的 `JobResult.retry_safe`，`_failure_result` 另要失败原因可被重跑清除（`failure_recoverability.is_transient_failure`）；超时（`_timeout_result`）与任务门禁拒绝（`_deterministic_failure`：没有 prompt、一次性任务的日预算超限、提示词注入扫描、工作流模板执行校验）恒为 `retry_safe=False`；recurring 任务的日预算超限不是失败：`_run_once` 返回 `JobResult(success=False, skipped=True, skip_reason="budget_blocked")` 并写一条 WARNING，executor 记为 SKIPPED、不计失败、任务保持 ACTIVE 到下一个常规时间点；`_run_with_retries` 遇到 `retry_safe=False` 的失败或任何跳过结果不再进程内重跑，只读工具（搜索、读文件）之后的瞬时失败仍可重跑；累积器在 `_run_once` 里创建并传给两个流消费者，超时或异常也读得到。 |
| `effectful_steps.py` | `has_effectful_tools(progress_steps)`：已记录的步骤里是否有对改变状态的工具（`completion_guard.is_mutating_tool`，注册表 fail-closed：未登记的工具视为会改变状态）的调用；没有工具名的步骤（进度标记）不计。重试决定（`agent_runner`）与后置复核门（`post_run_verification`）共用这一个定义。 |
| `failure_recoverability.py` | `is_transient_failure(exc)`：失败的原因重跑能否消失。agent 流的 `MyrmLLMError` 取它记录的 `error_code`（流在失败时已定下的原因，不重新解析文字），其余异常经 `classify_failover_reason` 现场分类；`FailoverReason.recoverability` 为 TRANSIENT（含未知原因）才可重跑，永久与半永久（密钥无效、上下文超限、余额耗尽、请求被拒）不可；`ConfigIncompleteError`（缺少必需设置）不可。`agent_runner._failure_result` 调用，重试决定与 `effectful_steps` 的副作用判定相互独立、取交集。 |
| `post_run_verification.py` | Cron 后置交付复核：当 Agent `cron_post_run_verify=true` 且 run 成功且检测到 mutating 工具使用时，spawn `adversarial-reviewer`（`verify_worker_output`，不重跑 worker；无结论的复核——Verifier 崩溃或未执行任何命令即给 PASS——记 `verification.status=error`，不追加失败注记）。effectful 判定：`effectful_steps.has_effectful_tools`（底层 `completion_guard.is_mutating_tool()`，registry fail-closed：未知工具视为 effectful；与重试决定共用）。注入 `metadata.deliverable_tier` 与 `metadata.verification`。结果经 `dataclasses.replace` 改写，`retry_safe` 等字段原样保留（`acceptance_verification.py` 同理）。 |
| `blocked_actions.py` | 本次运行被安全规则拦下的动作摘要：`blocked_actions_metadata(entries)` 只取 harness 审计日志里拒绝了所涉动作的决策（`is_blocking_decision`；只是把自动放行通道关上、动作转去审批提示的升级类不算），按（工具, 原因）合并计数，写入运行元数据 `blockedCount`（拦截总次数）与 `blockedActions`（至多 10 行 `{tool, reason, count}`，按首次出现排序）。原因经凭据脱敏、折成单行、截到 160 字符；一次都没拦下则不写任何键。`agent_runner._StreamAccumulator.to_result` 调用 |
| `research_lease.py` | 只读研究租约策略：`is_read_only_job` 判定作业声明的能力（空声明也算）是否全部落在租约放行工具的能力集合内；`grant_run_lease(agent, job, timeout_seconds, untrusted)` 在「只读作业」或「非所有者触发」时为本次运行授予租约，并把 `agent.approval_session_key` 换成私有键 `cron:{job.id}:{随机后缀}`（保留 `cron:` 前缀，审批中间件据此走无人值守分支）；`release_run_lease` 撤销租约。租约按审批会话键生效，私有键使同一作业的并发运行互不撤销、非所有者运行不与所有者运行共享拒绝计数。放行工具集即 harness `DEFAULT_READ_ONLY_TOOLS`（file_read / grep / glob / web_search / web_fetch），其余默认拒绝；声明了其他能力的作业不挂租约，按声明的能力运行。工作流模板作业不在覆盖内（其 agent 由工作流引擎自建，沿用不了该键），故不可信入口直接跳过该类作业。`agent_runner._run_once` 调用 |
| `channel_delivery.py` | ResultDelivery 协议实现：IM 渠道投递 + Webhook；Feishu/Lark **bot hook** 走 `feishu_bot_webhook.py`；WeCom **bot hook** 走 `wecom_bot_webhook.py`；构造函数可注入 `WebhookDelivery`（测试投递端点用于零重试快速验证）。群投递门禁：冻结身份拒收（fail-closed）、`DeliveryConfig.thread_id` 进串、主动元数据标记。IM 渠道经 `MessageBus.send_now` 投递，产出里的工作区交付物随消息作为附件（`channel_deliverables.py`）；Feishu/WeCom bot hook 与通用 webhook 保持纯文本 |
| `channel_deliverables.py` | Cron 产出 → IM 交付物（`channel_reply` 交付物装配的 cron 对应物）：扫描产出文本中的工作区相对路径（工作区取自 job 绑定 chat 的 `workspace_dir`，沙箱内解析、跳过代码块）→ `MediaAttachment`；超限/压缩提示按用户语言（`resolve_user_locale`）追加，仅剩附件时补「交付物已附上」；有附件才附带「在浏览器继续」网页接力按钮（文本路由/云托管出站降级为链接）。非临时的工作区文件不删，压缩副本为 `ephemeral`，在交给总线前被取消则就地清理 |
| `delivery_resolver.py` | Cron 工具 webhook URL → `DeliveryConfig`（非空 URL 均为 `webhook` channel，Agent 创建任务时生成 HMAC secret） |
| `feishu_bot_webhook.py` | Feishu/Lark 自定义机器人 hook：`msg_type=text` JSON POST |
| `wecom_bot_webhook.py` | WeCom (企业微信) 群机器人 hook：`msgtype=markdown` JSON POST |
| `inbound_event_dispatch.py` | 入站 IM 消息 → `CronScheduler.dispatch_event`（SSOT：`AgentRouter` 过滤后、且仅对访问策略放行的发送者调用）。派发前先过风控闸门 `screen_user_text`：作业上下文原样带着匹配的消息，命中的消息不拉起任何作业（筛查失败同样不派发）；命中记录与通知都由同一条消息的回合路径写与发，派发只检测不记录。必填 `untrusted`（发送者不是所有者）为真时在 harness `untrusted_ingress_scope` 内派发：调度器为每个命中作业派生的任务继承围栏标记，派发方自身（路由消费循环）不受影响 |
| `sqlalchemy_trigger_provider.py` | TriggerProvider 实现：event/system/webhook 匹配 |
| `stream_listener.py` | StreamListener 实现：出站 WS/SSE 长连接管理（重连 + 心跳 + filter 匹配 + 资源限制） |
| `poll_listener.py` | PollListener 实现：定时 HTTP 拉取 + 内容哈希变更检测 |
| `wiki_router_job_runner.py` | JobRunner：`JobType.ROUTER` 分发 `__wiki_source_sync__`、`__wiki_ima_sync__`（ima 时间盒同步切片，`JobResult.retry_at` 续跑/限流退避）、`__wiki_maintain__:{mode}` 与 `__wiki_daily_review_compound__`（每日复盘知识化汇总 + 停滞队列兜底 compile）至 wiki SSOT runners |

---

## 依赖关系

### 内部依赖
- `myrm_agent_harness.toolkits.cron`：CronManager, CronScheduler, WebhookDelivery, 协议定义
- `../../channel_bridge/`：ChannelGateway（channel_delivery 使用）；`agent_executor/deliverable` 路径扫描 + `locale_provider` 用户语言（channel_deliverables 使用）
- `../../../remote_access/mobile_deep_link`：网页接力按钮（channel_deliverables 使用）
- `../../channel_bridge/config_loader`：用户配置加载（agent_runner 使用）
- `../../../ai_agents/`：AgentFactory（agent_runner 使用）
- `../../../services/agent/profile/profile_resolver`：AgentProfileResolver（agent_runner 使用，agent_id 绑定时加载完整配置）
- `../../../services/chat/chat_service`：`ChatService.load_web_chat_history`（agent_runner 使用，Thread Automation 模式加载会话历史）
- `../../../services/memory/shared_context`：Shared Context 绑定解析（agent_runner 使用）
- `../../agent/stop_reason`：停止原因的存储形态与取舍（agent_runner 使用）
- `../../../database/`：CronJob / CronRun ORM

### 外部依赖
- `sqlalchemy`：ORM 操作
