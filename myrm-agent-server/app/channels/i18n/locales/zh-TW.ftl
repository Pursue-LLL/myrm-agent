mobile_hitl_open = 開啟手機審批
mobile_btw_open = 手機檢視結果
web_continue_chat = 在瀏覽器繼續

no_active_task_to_stop = ℹ 當前沒有正在執行的任務。
execution_stopped =  任務已停止。
placeholder_stopped =  任務已停止。
no_pending_approval = ℹ 沒有待審批的請求。
approval_processing =  正在處理審批...
approval_always_processing =  正在處理審批並加入永久允許列表...
approval_denial_processing =  正在處理拒絕...
approval_batch_processing =  正在處理 { $approve_count } 個批准、{ $reject_count } 個拒絕...
approval_batch_processing_always =  正在處理 { $approve_count } 個批准（含 { $always_count } 個永久）、{ $reject_count } 個拒絕...
approval_timeout_resolved = ℹ 該審批已被超時自動處理，無需操作。
permission_denied =  許可權不足：`/{ $cmd }` 需要管理員許可權。
usage_steer = 用法：`/steer <新指令>`
steering_applied = 指令已應用：_{ $preview }_
usage_queue = 用法：`/queue <任務描述>`
queue_queued = 已排隊，將在當前任務完成後執行。
queue_immediate = 當前沒有執行中的任務 — 立即執行。
goal_system_not_configured =  當前環境未配置目標系統。
goal_management_not_available = 目標管理不可用。
agent_is_running_goal = Agent 正在執行 — 請在執行中使用 /goal status、/goal pause 或 /goal clear。設定新目標前請先使用 /stop 停止 Agent。
usage_goal = 用法：`/goal <你的目標>`
goal_set =
    目標已設定：**{ $goal }**
    Agent 現在將開始工作。
goal_queued =
    目標已排隊：**{ $goal }**
    當前目標完成後將自動開始執行。
goal_active_exists =
    已有活動目標：**{ $objective }**
    請先使用 `/goal clear`，或使用 `/goal status` 檢視進度。
no_goal_is_set = 當前沒有設定目標。請使用 `/goal <目標>` 來設定。
no_active_goal_to_pause = 沒有可以暫停的活動目標。
no_active_goal_session = 未找到活動的目標會話。
no_active_goal_subgoals = 沒有可以管理子目標的活動目標。
goal_paused =
    目標已暫停：**{ $objective }**
    使用 `/goal resume` 繼續。
goal_wait =
    目標等待中：**{ $objective }**
    原因：{ $reason }
    使用 `/goal unwait` 恢復。
goal_unwait = 目標已從等待恢復：**{ $objective }**
goal_not_waiting = 目標未處於等待狀態。
goal_wait_not_supported = 當前環境不支援等待模式。
goal_resumed = 目標已恢復：**{ $objective }**
goal_cleared = 目標已清除：**{ $objective }**
goal_cannot_resume = 無法恢復處於「{ $status }」狀態的目標。
goal_budget_set = 當前目標預算已設為 **{ $max_turns } 輪**。
goal_status_queued = 排隊中
goal_status_label = 執行中
goal_status_paused = 已暫停
goal_status_pending_approval = 待審批
goal_status_budget_limited = 預算受限
goal_status_wait = 等待中
goal_status_complete = 已完成
goal_status_cancelled = 已取消
goal_status_needs_review = 需人工稽核
goal_status_header = **目標：** { $objective }
goal_status_line = **狀態：** { $status }
goal_budget_tokens = Token：{ $used }/{ $max }
goal_budget_turns = 輪數：{ $used }/{ $max }
goal_budget_header = **預算：** { $parts }
usage_subgoal_add = 用法：`/subgoal add <文字>`
subgoal_added = 已新增子目標：**{ $text }**
no_subgoals_defined = 當前目標沒有定義子目標。
current_subgoals = **當前子目標：**
usage_subgoal_remove = 用法：`/subgoal remove <索引>`
subgoal_removed = 已移除子目標：**{ $text }**
subgoal_index_out_of_range = 子目標索引 { $index } 超出範圍。
cleared_subgoals = 已清除 { $count } 個子目標。
no_active_goal_constraint = 未找到目標。請先使用 `/goal <目標>` 設定一個目標。
no_constraints_set = 當前目標未設定約束。
goal_constraint_added = 約束已新增：**{ $constraint }**
goal_constraints_cleared = 已清除所有約束。
goal_status_constraints = **約束：** { $items }
goal_status_criteria = **驗收標準：** { $items }
goal_status_subgoals = **子目標：** { $items }
no_goal_to_resume = 沒有可以恢復的目標。
goal_already_active = 目標已經處於活動狀態。
no_goal_to_clear = 沒有可以清除的目標。
no_active_goal_to_clear = 沒有可以清除的活動目標。
no_active_goal_set_first = 沒有活動目標。請先使用 `/goal <目標>` 設定一個目標。
no_active_goal_budget = 沒有可以設定預算的活動目標。
usage_goal_budget = 用法：`/goal budget <最大輪數>` — 例如 `/goal budget 10`
budget_at_least_one = 預算必須至少為 1。
invalid_budget = 無效的預算值。請使用數字，例如 `/goal budget 10`
background_tasks_not_available = 後臺任務不可用。
usage_btw = 用法：`/btw <任務>` | `/btw list` | `/btw cancel <id>` | `/btw steer <id> <指令>`
background_none = 沒有後臺任務。
background_header = **後臺任務**
background_cancel_usage = 用法：`/btw cancel <task_id>`
background_steer_usage = 用法：`/btw steer <task_id> <指令>`
background_cancelled = 任務 `{ $task_id }` 已取消。
background_not_found = 任務 `{ $task_id }` 未找到或已結束。
background_steer_ok = 已向 `{ $task_id }` 應用指令。
background_steer_fail = 任務 `{ $task_id }` 未找到或已結束。
background_started =
    後臺任務已啟動：`{ $task_id }`
    完成後將通知你。
background_completed =
    ✅ 後臺任務完成："{ $title }"
    { $result }
background_failed =
    ❌ 後臺任務失敗："{ $title }"
    { $result }
bash_bg_finish_title = 後臺任務已完成
bash_bg_finish_success =
    後臺任務已完成 (pid={ $pid })。
    命令：{ $command }
bash_bg_finish_with_error =
    後臺任務異常結束：{ $error_category } (pid={ $pid }, status={ $status }, exit_code={ $exit_code })。
    命令：{ $command }
bash_bg_finish_generic =
    後臺任務 { $status } (pid={ $pid }, exit_code={ $exit_code })。
    命令：{ $command }
goal_stream_failed_title = 目標需人工審查
goal_stream_failed_message =
    自主任務意外停止，請在目標面板檢視並繼續。
new_session_started =  新對話已開始，下一條訊息將開啟新會話。
compact_not_configured = ℹ 未配置壓縮功能。
compact_success =  上下文已壓縮：{ $message_count } 條訊息已摘要，約節省 { $tokens_saved } tokens。{ $topic_hint }
compact_skipped = ℹ 跳過壓縮：{ $reason }
compact_failed =  壓縮失敗：{ $error }
retry_not_configured = ℹ 未配置重試功能。
retry_nothing = ℹ 沒有可重試的內容。
retry_failed = ℹ 重試失敗。
retry_failed_error =  重試失敗：{ $error }
undo_not_configured = ℹ 未配置撤銷功能。
undo_nothing = ℹ 沒有可撤銷的內容。
undo_failed = ℹ 撤銷失敗。
undo_failed_error =  撤銷失敗：{ $error }
undo_success = ↩ 已撤銷：移除了 { $count } 條訊息。
undo_reverted = ↩ 已還原 { $count } 個檔案。
topic_not_configured = ℹ 未配置話題管理。
topic_bound =
     { $scope } 已繫結{ $agent_label }。
    使用 /unbind 解除繫結。
topic_unbound =  { $scope } 已解除繫結。
topic_no_binding = ℹ 此 { $scope } 沒有繫結。
topic_status =
     { $scope } 狀態
    { $agent_label }
    狀態：{ $status }{ $bound_label }
topic_no_binding_defaults =  此 { $scope } 無繫結（使用預設配置）。
topic_command_failed =  { $scope } 命令失敗：{ $error }
topic_scope_topic = 話題
topic_scope_channel = 頻道
topic_agent_switched = （智慧體：{ $from_agent } → { $to_agent }）
topic_agent_only = （智慧體：{ $agent_id }）
topic_status_agent = 智慧體：{ $agent_id }
topic_status_agent_default = 智慧體：預設
topic_status_bound_at =
    
    繫結時間：{ $bound_at }
topic_status_enabled = 已啟用
topic_status_disabled = 已禁用
yolo_off =  YOLO 模式 **關閉** — 工具呼叫需要審批
yolo_on_expires =  YOLO 模式 **開啟** — { $seconds } 秒後過期
yolo_off_expired =  YOLO 模式 **關閉**（已過期）
yolo_on_no_expiration =  YOLO 模式 **開啟**（無過期時間）
yolo_disabled =  YOLO 模式 **已關閉** — 工具審批已恢復
yolo_activated =
     **YOLO 模式已啟用** — 所有工具呼叫將自動批准
    
     **警告**：這將繞過所有安全檢查，請謹慎使用！
yolo_activated_timeout =
     **YOLO 模式已啟用** — { $timeout } 秒後過期
    
     **警告**：所有工具呼叫將自動批准，請謹慎使用！
yolo_already_off = ℹ YOLO 模式已經是關閉狀態
yolo_invalid =  無效的 YOLO 操作。用法：/yolo [on|off|toggle|status]
yolo_invalid_usage =  無效的 /yolo 命令。用法：`/yolo [on|off|toggle|status] [timeout_seconds]`
personality_header =  **可用個性風格**：
personality_list_fallback =  可用風格：
personality_current =
    
    
     當前會話風格：**{ $style }**
personality_reset =  個性已重置為 **Professional**（預設）
personality_activated =
    { $emoji } **{ $name }** 已啟用！
    
    { $description }
personality_set =  個性已設為 **{ $style }**
personality_invalid =  無效風格「{ $style }」。使用 `/personality list` 檢視可用選項。
status_header = **會話狀態**
status_session = • **會話：** `{ $session_id }`
status_title = • **標題：** { $title }
status_created = • **建立時間：** { $created_at }
status_last_activity = • **最後活動：** { $last_activity }
status_model = • **模型：** { $model_name }
status_tokens = • **Token：** { $total_tokens }
status_cost = • **費用：** ${ $total_usd }
status_calls = • **呼叫次數：** { $total_calls }
status_no_session = • 沒有活動會話
status_budget_header = 📊 **渠道預算**
status_budget_today = • 今日：${ $today_cost } / ${ $daily_limit }（{ $usage_pct }%）
status_agent_running = • **Agent：** 執行中
status_agent_idle = • **Agent：** 空閒
status_queued = • **排隊：** { $count }
status_yolo_on = • **YOLO：** 開啟
status_yolo_expires = • **YOLO：** 開啟（{ $seconds } 秒後過期）
help_header =  **可用命令**
skill_not_configured = ℹ 技能命令 /{ $cmd } 未配置。
skill_load_failed =  無法載入 /{ $cmd } 的技能。
pairing_pending = 您的訪問請求正在等待管理員審批。
pairing_submitted = 您的訪問請求已提交，管理員將盡快稽核。
mute_confirm = 已閉嘴，接下來我只會在被 @ 時回應。
search_not_configured = 當前智慧體需要網路搜尋能力，但搜尋服務尚未配置。請先在設定中新增並啟用搜尋服務。
search_unreachable = 搜尋服務已配置但當前無法連線。請檢查搜尋服務是否正常執行後重試。
daily_budget_blocked = 已達每日預算上限，執行被攔截。請在 Web 設定中調整預算限額後繼續使用。
channel_budget_blocked = 此頻道的每日預算已用完。其他頻道和 Web 會話不受影響。頻道所有者可在設定 > 預算中調整限額。
cooldown_retry =
    
    
    ⏱️ 請在 {seconds:.0f} 秒後重試。
config_next_steps =
    
    
    後續步驟：
    { $steps }
component_options_prefix = 選項
component_quick_reply_instruction = ↩ 回覆數字選擇
placeholder_thinking =  思考中...
placeholder_no_response =  未生成回覆。
draft_review_pending = ✏️ 回覆已生成草稿，等待稽核後傳送。
draft_review_reason = AI 生成的回覆需要稽核後才能傳送至頻道。
placeholder_execution_error =  錯誤：{ $error }
placeholder_request_timeout =  請求超時。
placeholder_retrying =
    
    
    [重試中... { $attempt }/{ $max_retries }]
error_rate_limit = API 速率限制 — 模型暫時無法生成回覆，請稍後再試。
error_overloaded = AI 服務暫時過載，請稍後再試。
error_billing = 因配置問題服務暫時不可用，請聯絡管理員。
error_auth = 因配置問題服務暫時不可用，請聯絡管理員。
error_timeout = 請求超時，請重試。
error_context_overflow = 對話過長，請開始新會話。
error_format = AI 生成了無效格式，請重試。
error_model_not_found = 請求的模型不可用，請選擇其他模型。
error_safety_block = 請求被安全過濾器攔截。
error_response_format = AI 生成了無效格式，請重試。
error_unknown = 處理請求時出現問題，請稍後再試。
cmd_stop = 停止當前正在執行的 Agent 任務
cmd_new = 開始新的對話會話
cmd_compact = 壓縮對話上下文以減少 token 消耗
cmd_retry = 重試上一條訊息
cmd_undo = 刪除最後一輪使用者/助手對話
cmd_yolo = 切換 YOLO 模式（跳過工具審批）
cmd_personality = 切換會話個性風格
cmd_bind = 將智慧體繫結到此話題或頻道
cmd_unbind = 解除智慧體與此話題/頻道的繫結
cmd_topic = 顯示當前話題/頻道繫結狀態
cmd_goal = 設定、管理或檢視跨輪次持久目標
cmd_subgoal = 動態新增/移除/列出執行中目標的子目標
cmd_steer = 在 Agent 執行中注入新指令進行糾偏
cmd_queue = 將任務排隊，在當前任務完成後執行
cmd_background = 在獨立後臺會話中執行任務，不阻塞當前對話
cmd_status = 顯示當前會話狀態（token、費用、模型、Agent 狀態）
cmd_help = 顯示可用命令
cat_Session = 會話
cat_Configuration = 配置
cat_Topic = 話題
cat_Goals = 目標
cat_Execution = 執行
cat_Info = 資訊
cmd_handoff = 將當前對話轉移到其他平臺/渠道
usage_handoff = 用法：`/handoff <目標渠道>`
handoff_success =
     對話已轉移至 **{ $target }**。
    你現在可以在 { $target } 上繼續此對話。
handoff_no_target = 請指定目標渠道。用法：`/handoff <目標渠道>`
handoff_channel_not_found = 渠道 `{ $target }` 未找到或未連線。
handoff_no_pairing = 在 `{ $target }` 上沒有找到使用者配對。請先在該渠道傳送一條訊息以建立連線。
handoff_same_channel = 當前已在此渠道 — 無需轉移。
handoff_failed = 交接失敗：{ $error }
help_alias = （別名：{ $aliases }）
kanban_not_available = 看板任務管理不可用。
kanban_usage =
    📋 **看板命令：**
    `/kanban list` — 列出任務
    `/kanban show <id>` — 任務詳情
    `/kanban create <標題>` — 建立任務
    `/kanban comment <id> <訊息>` — 新增評論
    `/kanban edit <id> title|desc <文字>` — 編輯任務
    `/kanban complete <id>` — 標記完成
    `/kanban block <id> [原因]` — 阻塞
    `/kanban unblock <id>` — 解除阻塞
    `/kanban archive <id>` — 歸檔
    `/kanban stats` — 看板統計
kanban_error = ❌ 看板命令執行失敗，請檢查語法後重試。
session_reset_notify_idle = ℹ️ 會話已自動重置：超過 { $minutes } 分鐘無活動。當前為全新對話。
session_reset_notify_daily = ℹ️ 會話已自動重置：每日 { $hour }:00 UTC 定時重置。當前為全新對話。
memory_unavailable = ℹ 記憶系統不可用。
memory_no_pending = ℹ 沒有待審批的記憶。
memory_pending_header = 📋 **待審批記憶** ({ $count })：
memory_pending_hint = 使用 `/memory approve <id>` 或 `/memory reject <id>` 審批，或 `/memory approve all` 一鍵全部批准。
memory_approved = ✅ 記憶 `{ $id }` 已批准。
memory_rejected = ❌ 記憶 `{ $id }` 已拒絕。
memory_approved_all = ✅ 已批准 { $count } 條待審批記憶。
memory_not_found = ℹ 未找到匹配 `{ $id }` 的待審批記憶。
memory_error = ❌ 記憶命令執行失敗，請重試。
cmd_memory = 檢視並審批待確認的記憶寫入
cmd_learn = 從 URL、檔案或對話中教 Agent 學習新技能
cat_Memory = 記憶
cat_Skills = 技能
learn_not_configured = ℹ 當前環境未配置技能學習功能。
learn_failed = ❌ 構建學習提示失敗，請重試。
reassurance_still_running = ⚓ 仍在處理中（已完成 { $steps } 個步驟{ $stage }）—— 請稍等
agent_picker_no_agents = 未配置任何智慧體。
agent_picker_select = 選擇一個智慧體：
agent_picker_switched = 已切換至：{ $name }
artifact_deep_link = 💻 檢視互動網頁
artifact_deep_link_named = 💻 { $filename }
