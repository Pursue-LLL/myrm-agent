mobile_hitl_open = 打开手机审批
mobile_btw_open = 手机查看结果
web_continue_chat = 在浏览器继续

no_active_task_to_stop = ℹ 当前没有正在执行的任务。
execution_stopped =  任务已停止。
placeholder_stopped =  任务已停止。
no_pending_approval = ℹ 没有待审批的请求。
approval_processing =  正在处理审批...
approval_always_processing =  正在处理审批并加入永久允许列表...
approval_denial_processing =  正在处理拒绝...
approval_batch_processing =  正在处理 { $approve_count } 个批准、{ $reject_count } 个拒绝...
approval_batch_processing_always =  正在处理 { $approve_count } 个批准（含 { $always_count } 个永久）、{ $reject_count } 个拒绝...
approval_timeout_resolved = ℹ 该审批已被超时自动处理，无需操作。
permission_denied =  权限不足：`/{ $cmd }` 需要管理员权限。
usage_steer = 用法：`/steer <新指令>`
steering_applied = 指令已应用：_{ $preview }_
usage_queue = 用法：`/queue <任务描述>`
queue_queued = 已排队，将在当前任务完成后执行。
queue_immediate = 当前没有运行中的任务 — 立即执行。
goal_system_not_configured =  当前环境未配置目标系统。
goal_management_not_available = 目标管理不可用。
agent_is_running_goal = Agent 正在运行 — 请在运行中使用 /goal status、/goal pause 或 /goal clear。设置新目标前请先使用 /stop 停止 Agent。
usage_goal = 用法：`/goal <你的目标>`
goal_set =
    目标已设定：**{ $goal }**
    Agent 现在将开始工作。
goal_queued =
    目标已排队：**{ $goal }**
    当前目标完成后将自动开始执行。
goal_active_exists =
    已有活动目标：**{ $objective }**
    请先使用 `/goal clear`，或使用 `/goal status` 查看进度。
no_goal_is_set = 当前没有设定目标。请使用 `/goal <目标>` 来设定。
no_active_goal_to_pause = 没有可以暂停的活动目标。
no_active_goal_session = 未找到活动的目标会话。
no_active_goal_subgoals = 没有可以管理子目标的活动目标。
goal_paused =
    目标已暂停：**{ $objective }**
    使用 `/goal resume` 继续。
goal_wait =
    目标等待中：**{ $objective }**
    原因：{ $reason }
    使用 `/goal unwait` 恢复。
goal_unwait = 目标已从等待恢复：**{ $objective }**
goal_not_waiting = 目标未处于等待状态。
goal_wait_not_supported = 当前环境不支持等待模式。
goal_resumed = 目标已恢复：**{ $objective }**
goal_cleared = 目标已清除：**{ $objective }**
goal_cannot_resume = 无法恢复处于「{ $status }」状态的目标。
goal_budget_set = 当前目标预算已设为 **{ $max_turns } 轮**。
goal_status_queued = 排队中
goal_status_label = 运行中
goal_status_paused = 已暂停
goal_status_pending_approval = 待审批
goal_status_budget_limited = 预算受限
goal_status_wait = 等待中
goal_status_complete = 已完成
goal_status_cancelled = 已取消
goal_status_needs_review = 需人工审核
goal_status_header = **目标：** { $objective }
goal_status_line = **状态：** { $status }
goal_budget_tokens = Token：{ $used }/{ $max }
goal_budget_turns = 轮数：{ $used }/{ $max }
goal_budget_header = **预算：** { $parts }
usage_subgoal_add = 用法：`/subgoal add <文本>`
subgoal_added = 已添加子目标：**{ $text }**
no_subgoals_defined = 当前目标没有定义子目标。
current_subgoals = **当前子目标：**
usage_subgoal_remove = 用法：`/subgoal remove <索引>`
subgoal_removed = 已移除子目标：**{ $text }**
subgoal_index_out_of_range = 子目标索引 { $index } 超出范围。
cleared_subgoals = 已清除 { $count } 个子目标。
no_active_goal_constraint = 未找到目标。请先使用 `/goal <目标>` 设定一个目标。
no_constraints_set = 当前目标未设置约束。
goal_constraint_added = 约束已添加：**{ $constraint }**
goal_constraints_cleared = 已清除所有约束。
goal_status_constraints = **约束：** { $items }
goal_status_criteria = **验收标准：** { $items }
goal_status_subgoals = **子目标：** { $items }
no_goal_to_resume = 没有可以恢复的目标。
goal_already_active = 目标已经处于活动状态。
no_goal_to_clear = 没有可以清除的目标。
no_active_goal_to_clear = 没有可以清除的活动目标。
no_active_goal_set_first = 没有活动目标。请先使用 `/goal <目标>` 设定一个目标。
no_active_goal_budget = 没有可以设置预算的活动目标。
usage_goal_budget = 用法：`/goal budget <最大轮数>` — 例如 `/goal budget 10`
budget_at_least_one = 预算必须至少为 1。
invalid_budget = 无效的预算值。请使用数字，例如 `/goal budget 10`
background_tasks_not_available = 后台任务不可用。
usage_btw = 用法：`/btw <任务>` | `/btw list` | `/btw cancel <id>` | `/btw steer <id> <指令>`
background_none = 没有后台任务。
background_header = **后台任务**
background_cancel_usage = 用法：`/btw cancel <task_id>`
background_steer_usage = 用法：`/btw steer <task_id> <指令>`
background_cancelled = 任务 `{ $task_id }` 已取消。
background_not_found = 任务 `{ $task_id }` 未找到或已结束。
background_steer_ok = 已向 `{ $task_id }` 应用指令。
background_steer_fail = 任务 `{ $task_id }` 未找到或已结束。
background_started =
    后台任务已启动：`{ $task_id }`
    完成后将通知你。
background_completed =
    ✅ 后台任务完成："{ $title }"
    { $result }
background_failed =
    ❌ 后台任务失败："{ $title }"
    { $result }
bash_bg_finish_title = 后台任务已完成
bash_bg_finish_success =
    后台任务已完成 (pid={ $pid })。
    命令：{ $command }
bash_bg_finish_with_error =
    后台任务异常结束：{ $error_category } (pid={ $pid }, status={ $status }, exit_code={ $exit_code })。
    命令：{ $command }
bash_bg_finish_generic =
    后台任务 { $status } (pid={ $pid }, exit_code={ $exit_code })。
    命令：{ $command }
goal_stream_failed_title = 目标需人工审查
goal_stream_failed_message =
    自主任务意外停止，请在目标面板查看并继续。
new_session_started =  新对话已开始，下一条消息将开启新会话。
compact_not_configured = ℹ 未配置压缩功能。
compact_success =  上下文已压缩：{ $message_count } 条消息已摘要，约节省 { $tokens_saved } tokens。{ $topic_hint }
compact_skipped = ℹ 跳过压缩：{ $reason }
compact_failed =  压缩失败：{ $error }
retry_not_configured = ℹ 未配置重试功能。
retry_nothing = ℹ 没有可重试的内容。
retry_failed = ℹ 重试失败。
retry_failed_error =  重试失败：{ $error }
retry_reverted = ↩ 重试前已还原 { $count } 个文件。
retry_files_not_revertible = ↩ 重试前有 { $count } 个文件变更无法自动还原（文件过大或缓冲区已满）。
undo_not_configured = ℹ 未配置撤销功能。
undo_nothing = ℹ 没有可撤销的内容。
undo_failed = ℹ 撤销失败。
undo_failed_error =  撤销失败：{ $error }
undo_success = ↩ 已撤销：移除了 { $count } 条消息。
undo_reverted = ↩ 已还原 { $count } 个文件。
undo_files_not_revertible = ↩ 有 { $count } 个文件变更无法自动还原（文件过大或缓冲区已满）。
topic_not_configured = ℹ 未配置话题管理。
topic_search_agent_rejected =
    搜索类智能体不能绑定到渠道。
    请绑定 General 智能体；轻量搜索请使用 Web Fast 模式。
topic_bound =
     { $scope } 已绑定{ $agent_label }。
    使用 /unbind 解除绑定。
topic_unbound =  { $scope } 已解除绑定。
topic_no_binding = ℹ 此 { $scope } 没有绑定。
topic_status =
     { $scope } 状态
    { $agent_label }
    状态：{ $status }{ $bound_label }
topic_no_binding_defaults =  此 { $scope } 无绑定（使用默认配置）。
topic_command_failed =  { $scope } 命令失败：{ $error }
topic_scope_topic = 话题
topic_scope_channel = 频道
topic_agent_switched = （智能体：{ $from_agent } → { $to_agent }）
topic_agent_only = （智能体：{ $agent_id }）
topic_status_agent = 智能体：{ $agent_id }
topic_status_agent_default = 智能体：默认
topic_status_bound_at =
    
    绑定时间：{ $bound_at }
topic_status_enabled = 已启用
topic_status_disabled = 已禁用
yolo_off =  YOLO 模式 **关闭** — 工具调用需要审批
yolo_on_expires =  YOLO 模式 **开启** — { $seconds } 秒后过期
yolo_off_expired =  YOLO 模式 **关闭**（已过期）
yolo_on_no_expiration =  YOLO 模式 **开启**（无过期时间）
yolo_disabled =  YOLO 模式 **已关闭** — 工具审批已恢复
yolo_activated =
     **YOLO 模式已激活** — 所有工具调用将自动批准
    
     **警告**：这将绕过所有安全检查，请谨慎使用！
yolo_activated_timeout =
     **YOLO 模式已激活** — { $timeout } 秒后过期
    
     **警告**：所有工具调用将自动批准，请谨慎使用！
yolo_already_off = ℹ YOLO 模式已经是关闭状态
yolo_invalid =  无效的 YOLO 操作。用法：/yolo [on|off|toggle|status]
yolo_invalid_usage =  无效的 /yolo 命令。用法：`/yolo [on|off|toggle|status] [timeout_seconds]`
personality_header =  **可用个性风格**：
personality_list_fallback =  可用风格：
personality_current =
    
    
     当前会话风格：**{ $style }**
personality_reset =  个性已重置为 **Professional**（默认）
personality_activated =
    { $emoji } **{ $name }** 已激活！
    
    { $description }
personality_set =  个性已设为 **{ $style }**
personality_invalid =  无效风格「{ $style }」。使用 `/personality list` 查看可用选项。
status_header = **会话状态**
status_session = • **会话：** `{ $session_id }`
status_title = • **标题：** { $title }
status_created = • **创建时间：** { $created_at }
status_last_activity = • **最后活动：** { $last_activity }
status_model = • **模型：** { $model_name }
status_tokens = • **Token：** { $total_tokens }
status_cost = • **费用：** ${ $total_usd }
status_calls = • **调用次数：** { $total_calls }
status_no_session = • 没有活动会话
status_budget_header = 📊 **渠道预算**
status_budget_today = • 今日：${ $today_cost } / ${ $daily_limit }（{ $usage_pct }%）
status_agent_running = • **Agent：** 运行中
status_agent_idle = • **Agent：** 空闲
status_queued = • **排队：** { $count }
status_yolo_on = • **YOLO：** 开启
status_yolo_expires = • **YOLO：** 开启（{ $seconds } 秒后过期）
help_header =  **可用命令**
skill_not_configured = ℹ 技能命令 /{ $cmd } 未配置。
skill_load_failed =  无法加载 /{ $cmd } 的技能。
pairing_pending = 您的访问请求正在等待管理员审批。
pairing_submitted = 您的访问请求已提交，管理员将尽快审核。
mute_confirm = 已闭嘴，接下来我只会在被 @ 时回应。
search_not_configured = 当前智能体需要网络搜索能力，但搜索服务尚未配置。请先在设置中添加并启用搜索服务。
search_unreachable = 搜索服务已配置但当前无法连接。请检查搜索服务是否正常运行后重试。
daily_budget_blocked = 已达每日预算上限，执行被拦截。请在 Web 设置中调整预算限额后继续使用。
channel_budget_blocked = 此频道的每日预算已用完。其他频道和 Web 会话不受影响。频道所有者可在设置 > 预算中调整限额。
cooldown_retry =
    
    
    ⏱️ 请在 {seconds:.0f} 秒后重试。
config_next_steps =
    
    
    后续步骤：
    { $steps }
component_options_prefix = 选项
component_quick_reply_instruction = ↩ 回复数字选择
placeholder_thinking =  思考中...
placeholder_no_response =  未生成回复。
draft_review_pending = ✏️ 回复已生成草稿，等待审核后发送。
draft_review_reason = AI 生成的回复需要审核后才能发送至频道。
placeholder_execution_error =  错误：{ $error }
placeholder_request_timeout =  请求超时。
placeholder_retrying =
    
    
    [重试中... { $attempt }/{ $max_retries }]
error_rate_limit = API 速率限制 — 模型暂时无法生成回复，请稍后再试。
error_overloaded = AI 服务暂时过载，请稍后再试。
error_billing = 因配置问题服务暂时不可用，请联系管理员。
error_auth = 因配置问题服务暂时不可用，请联系管理员。
error_timeout = 请求超时，请重试。
error_context_overflow = 对话过长，请开始新会话。
error_format = AI 生成了无效格式，请重试。
error_model_not_found = 请求的模型不可用，请选择其他模型。
error_safety_block = 请求被安全过滤器拦截。
error_response_format = AI 生成了无效格式，请重试。
error_unknown = 处理请求时出现问题，请稍后再试。
cmd_stop = 停止当前正在运行的 Agent 任务
cmd_new = 开始新的对话会话
cmd_compact = 压缩对话上下文以减少 token 消耗
cmd_retry = 重试上一条消息
cmd_undo = 删除最后一轮用户/助手对话
cmd_yolo = 切换 YOLO 模式（跳过工具审批）
cmd_personality = 切换会话个性风格
cmd_bind = 将智能体绑定到此话题或频道
cmd_unbind = 解除智能体与此话题/频道的绑定
cmd_topic = 显示当前话题/频道绑定状态
cmd_goal = 设定、管理或查看跨轮次持久目标
cmd_subgoal = 动态添加/移除/列出运行中目标的子目标
cmd_steer = 在 Agent 运行中注入新指令进行纠偏
cmd_queue = 将任务排队，在当前任务完成后执行
cmd_background = 在独立后台会话中运行任务，不阻塞当前对话
cmd_status = 显示当前会话状态（token、费用、模型、Agent 状态）
cmd_help = 显示可用命令
cat_Session = 会话
cat_Configuration = 配置
cat_Topic = 话题
cat_Goals = 目标
cat_Execution = 执行
cat_Info = 信息
cmd_handoff = 将当前对话转移到其他平台/渠道
usage_handoff = 用法：`/handoff <目标渠道>`
handoff_success =
     对话已转移至 **{ $target }**。
    你现在可以在 { $target } 上继续此对话。
handoff_no_target = 请指定目标渠道。用法：`/handoff <目标渠道>`
handoff_channel_not_found = 渠道 `{ $target }` 未找到或未连接。
handoff_no_pairing = 在 `{ $target }` 上没有找到用户配对。请先在该渠道发送一条消息以建立连接。
handoff_same_channel = 当前已在此渠道 — 无需转移。
handoff_failed = 交接失败：{ $error }
help_alias = （别名：{ $aliases }）
kanban_not_available = 看板任务管理不可用。
kanban_usage =
    📋 **看板命令：**
    `/kanban list` — 列出任务
    `/kanban show <id>` — 任务详情
    `/kanban create <标题>` — 创建任务
    `/kanban comment <id> <消息>` — 添加评论
    `/kanban edit <id> title|desc <文本>` — 编辑任务
    `/kanban complete <id>` — 标记完成
    `/kanban block <id> [原因]` — 阻塞
    `/kanban unblock <id>` — 解除阻塞
    `/kanban archive <id>` — 归档
    `/kanban stats` — 看板统计
kanban_error = ❌ 看板命令执行失败，请检查语法后重试。
session_reset_notify_idle = ℹ️ 会话已自动重置：超过 { $minutes } 分钟无活动。当前为全新对话。
session_reset_notify_daily = ℹ️ 会话已自动重置：每日 { $hour }:00 UTC 定时重置。当前为全新对话。
memory_unavailable = ℹ 记忆系统不可用。
memory_no_pending = ℹ 没有待审批的记忆。
memory_pending_header = 📋 **待审批记忆** ({ $count })：
memory_pending_hint = 使用 `/memory approve <id>` 或 `/memory reject <id>` 审批，或 `/memory approve all` 一键全部批准。
memory_approved = ✅ 记忆 `{ $id }` 已批准。
memory_rejected = ❌ 记忆 `{ $id }` 已拒绝。
memory_approved_all = ✅ 已批准 { $count } 条待审批记忆。
memory_not_found = ℹ 未找到匹配 `{ $id }` 的待审批记忆。
memory_error = ❌ 记忆命令执行失败，请重试。
cmd_memory = 查看并审批待确认的记忆写入
cmd_learn = 从 URL、文件或对话中教 Agent 学习新技能
cat_Memory = 记忆
cat_Skills = 技能
learn_not_configured = ℹ 当前环境未配置技能学习功能。
learn_failed = ❌ 构建学习提示失败，请重试。
reassurance_still_running = ⏳ 工作中 — { $elapsed } 分钟（{ $steps } 步{ $stage }）
agent_picker_no_agents = 未配置任何智能体。
agent_picker_select = 选择一个智能体：
agent_picker_switched = 已切换至：{ $name }
artifact_deep_link = 💻 查看交互网页
artifact_deep_link_named = 💻 { $filename }
