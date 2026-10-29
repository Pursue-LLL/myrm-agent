# adaptive_wakeup/

## 架构概述

后台命令与子智能体完成（结算）后，服务端按有界预算决定这次完成对会话的去向，并只在会话空闲、用户没有叫停时起一轮唤醒回合。每次完成都会在聊天里留一条通知行（`extra_data["wakeup_notice"]` 标记其种类），下一轮（唤醒的或用户发起的）都能读到；界面上起了回合的通知隐藏在回答之后，没起回合的显示为一行安静的提示。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 门面 | 对外入口 `AdaptiveWakeupService`、`get_adaptive_wakeup_service` | ✅ |
| `service.py` | ✅ 核心 | `AdaptiveWakeupService.handle_settlement(event)`：会话已删则丢弃（返回 `None`）；harness 路由只「看」预算与用户停止标记 — 预算内 FOLLOWUP、超额 DEGRADE、用户已停止 SUPPRESS；发布 UI 通知事件、无论哪种去向都写一条通知行（消息 id 为 `wakeup_<种类>_<来源 id>`，同一来源重复结算不产生重复行；通知里的摘要与错误文本做最小 XML 转义并限长），只有 FOLLOWUP 调度唤醒回合。`note_results_read` 接收 harness 上报的「智能体已读到这些结果」；起回合前由 `_skip_reason` 再核对：E-Stop、用户已停止、用户在通知之后发过言、智能体已读到这轮要交付的全部结果、日预算超额、唤醒预算已用完，都不起；预算最后才扣（一个回合扣一次，同时落地的多个结算共用一轮）；回合正常结束且有回复时，把回复交给 `reply_return.return_wake_reply`。`record_human_turn`（用户发言：恢复额度、解除停止）、`record_user_stop`（Stop 端点与目标暂停/取消：停止后到期的完成不会起回合）、`forget_chat`（会话销毁时丢弃该会话的预算、停止标记与未交付的结算记录） | ✅ |
| `settled_results.py` | ✅ 叶子 | `SettledResults`：每个会话记两样东西——下一个唤醒回合要交付的结算（`queue`）、智能体在自己的回合里已经读到的结果（`mark_read`，每会话最多留 200 个，最旧的先丢）。唤醒回合取得会话时 `take_all_read` 一次取走并清掉：交付的结算非空且全部已读才返回 `True`；之后落地的结算属于下一个唤醒回合 | ✅ |
| `wake_turn_scheduler.py` | ✅ 叶子 | `schedule_wake_turn(chat_id, runner)`：唤醒回合的唯一发起处，只管排队与让路，不判断「该不该起」。同一会话已有排队唤醒时合并（只刷新完成时刻）；会话忙时有界等待（上限取网关的目标回合上限）：忙指应用网关占着会话（应用内回合、目标回合、其他唤醒回合），或 `chat_busy` 探针说所有者正在这条 IM 私聊里跑回合（IM 回合由路由的会话闸门串行，应用网关看不见），两者都空闲才取会话，取会话与上一次判断之间没有 `await`；轮到时在 `server_turn_lease` 下调用 runner，令牌即 Stop / 目标暂停 / E-Stop 翻转的那一个。排队项只由取得会话的那个唤醒移出，运行中到达的完成排成下一个唤醒 | ✅ |
| `wake_turn_stream.py` | ✅ 核心 | `stream_wake_turn(chat_id, turn_id, cancel_token)`：用该会话自己的智能体（会话行的 `agent_id`）构建并流式执行一轮唤醒；事件按会话 id 发布到事件总线，已生成的内容照常落库。仅在「还没给用户看到任何内容」时重试（最多 3 次）；已有内容后失败、或重试用尽，则发布 `error_kind=wake_turn_failed` 的错误事件并把这轮回复标成失败，而不是静默；令牌被取消时发 `agent_cancelled`、不再重试。请求带着会话行的无痕标记（`incognito_mode=chat.is_incognito`），无痕会话的唤醒回合与它自己的回合一样不写记忆。回复已落库之后，函数把这轮说的话（去掉首尾空白）作为返回值交回调用方；被 Stop、以错误结束（`completionStatus` 或停止原因的类别是 `cancelled` / `error`）、重试用尽或回复为空的回合返回 `None` | ✅ |
| `chat_busy.py` | ✅ 叶子 | 唤醒回合起之前问「这条会话是否有应用网关之外的回合占着」的端口：`ChatBusyProbe` 协议（一个同步方法 `is_busy(chat_id)`）、`set_chat_busy_probe`（注册 / 清除探针）、`is_chat_busy`（没有探针就是不忙；探针抛错只记警告并按不忙处理，等一个坏掉的探针只会丢掉这轮唤醒）。必须同步：调度器在得到答案的同一步里取会话，中间不能有 `await`。探针由渠道桥在网关运行期间注册（`core/channel_bridge/setup.py`） | ✅ |
| `reply_return.py` | ✅ 叶子 | 唤醒回合回复的出口端口：`WakeReplyReturner` 协议（一个方法 `return_reply(chat_id, reply)`）、`set_wake_reply_returner`（注册 / 清除承载方）、`return_wake_reply`（没有承载方就什么都不做；承载方抛错只记警告，不影响已结束的回合）。承载方由渠道桥在网关运行期间注册（`core/channel_bridge/setup.py`） | ✅ |

## 边界

- 本包只决定「要不要起、何时起、起了怎么跑」；入口 `../wakeup_handler.py`（子智能体）与 `../background_job/background_job_finish_handler.py`（后台命令）负责把 harness 会话键 `chat_<id>` 换回会话 id，本包内一律使用会话 id。
- 调用点由 `tests/services/agent/turn_lease/test_server_started_turns_guard.py` 钉死：`schedule_wake_turn` 与 `stream_wake_turn` 都只能由 `service.py` 调用，且 `wake_turn_scheduler.py` 必须在 `server_turn_lease` 下跑 runner。
- 「已读」来自 harness 的 `subagent_control_tool(action=list)`：它返回已完结子智能体的结果时经 `utils/runtime/wakeup_registry.report_results_read` 上报，入口 `../wakeup_handler.py::on_results_read` 把 harness 会话键换回会话 id 后交给 `note_results_read`。`subagent_control_tool(action=wait)` 取回已完结子智能体的结果（完成，或失败、超时、预算取消）时走同一条路；等待超时而子智能体仍在后台跑的不算（它之后结算时照常唤醒）。仍在运行、被等待的子智能体本来就不唤醒（harness 的 `awaited_children`）。智能体只读到一部分结果、或一个都没读，唤醒回合照常起。
- 预算与停止标记按会话记在 harness 的 `AdaptiveWakeupRouter`（`agent/coordination/adaptive_wakeup/`），本包不重复持有；`service.py` 经路由的 `claim_wake_turn` 在回合真正开始时扣一次额度。
- 用户发言的登记点是 `stream_session/chat_history_bootstrap.persist_user_message`（Web）与 `core/channel_bridge/executor_helpers/history.persist_and_load_history`（IM）；Stop 的登记点是 `api/agents/general_agent/streaming.py` 的两个取消端点与 `goals/goal_controls.stop_goal_turn`（暂停/取消目标），目标恢复经 `note_goal_resumed` 解除；会话销毁经 `services/chat/chat_disposal.clear_runtime_caches` 调 `forget_chat`。
- 通知行的种类标记常量在 `app/database/models/chat.py`（`WAKEUP_NOTICE_*`），判定函数 `is_wakeup_notice` 在 `app/services/chat/chat_helpers.py`；没起回合的种类（降级、抑制）不算用户轮次，`get_last_user_message` 跳过它们。
- 通知行是 `role=user` 的行，所以凡是统计「人说了什么」的读取处都要把它排除：SQL 侧用 `app/database/models/chat.py` 的 `NOT_WAKEUP_NOTICE`（陪伴活跃天数与消息数、成长看板的周消息数、会话分析的消息计数、行为测量的 Web 会话收集），Python 侧用 `is_wakeup_notice`（重试记忆提取找最近一轮）。消息 id 以 `wakeup_` 开头、没有标记的通知行由 `app/database/migrations.py::BACKFILL_LEGACY_WAKEUP_NOTICE_SQL` 一次性补上 `followup` 标记。
- 唤醒回合的回复总是先落进该会话（WebUI 可见）；其中来自所有者 IM 私聊的会话，回复随后经 `reply_return` 端口交给渠道桥（`core/channel_bridge/wake_return/`），由路由按普通回复的规则送回那条私聊（静默过滤、网页接力按钮、话题草稿审核都生效；回复正文点名的工作区文件作为附件随回复送出）。这条私聊里所有者的回合还在跑时，唤醒回合等它结束再起（`chat_busy` 端口）：回合里读过全部结果的，唤醒回合随后不起，不会把同一个结果在 IM 里说两遍；反方向（唤醒回合运行期间所有者发来的消息）不受此保护，两者并行。群聊与访客会话不回投：唤醒回合带着所有者的全部记忆，而那些会话运行在记忆隔离舱里。没有登记过来源的会话（在应用里开始的、或重启之前的）只留在会话里。

## 依赖

- harness `agent/coordination/adaptive_wakeup`（路由、预算、事件类型）、`agent/security/guards/estop`（`check_estop`）、`utils/runtime/cancellation`
- `app/services/agent/gateway.py`（会话占用判断）、`app/services/agent/turn_lease`（租约）
- `app/services/chat`（通知行落库、会话行、历史）、`app/services/event/app_event_bus`（UI 通知与流式事件）、`app/services/budget/enforcer`（日预算）
