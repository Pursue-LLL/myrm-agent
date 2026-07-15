mobile_hitl_open = Open mobile approval
mobile_btw_open = View on mobile
web_continue_chat = Continue in browser

no_active_task_to_stop = ℹ No active task to stop.
execution_stopped =  Execution stopped.
placeholder_stopped =  Execution stopped.
no_pending_approval = ℹ No pending approval requests.
approval_processing =  Processing approval...
approval_always_processing =  Approving and adding to allow-always list...
approval_denial_processing =  Processing denial...
approval_batch_processing =  Processing { $approve_count } approvals, { $reject_count } rejections...
approval_batch_processing_always =  Processing { $approve_count } approvals ({ $always_count } always), { $reject_count } rejections...
approval_timeout_resolved = ℹ This approval has already been resolved by timeout. No action needed.
permission_denied =  Permission denied: `/{ $cmd }` requires admin access.
usage_steer = Usage: `/steer <new instruction>`
steering_applied = Steering applied: _{ $preview }_
usage_queue = Usage: `/queue <task description>`
queue_queued = Queued. Will execute after the current task completes.
queue_immediate = No active task — executing immediately.
goal_system_not_configured =  Goal system is not configured in this environment.
goal_management_not_available = Goal management is not available.
agent_is_running_goal = Agent is running — use /goal status, /goal pause, or /goal clear mid-run. Stop the agent first with /stop before setting a new goal.
usage_goal = Usage: `/goal <your objective>`
goal_set =
    Goal set: **{ $goal }**
    Agent will start working on it now.
goal_queued =
    Goal queued: **{ $goal }**
    It will start automatically after the current goal finishes.
goal_active_exists =
    A goal is already active: **{ $objective }**
    Use `/goal clear` first, or `/goal status` to check progress.
no_goal_is_set = No goal is set. Use `/goal <objective>` to set one.
no_active_goal_to_pause = No active goal to pause.
no_active_goal_session = No active goal session found.
no_active_goal_subgoals = No active goal to manage subgoals for.
goal_paused =
    Goal paused: **{ $objective }**
    Use `/goal resume` to continue.
goal_resumed = Goal resumed: **{ $objective }**
goal_cleared = Goal cleared: **{ $objective }**
goal_cannot_resume = Cannot resume goal in '{ $status }' state.
goal_budget_set = Budget set to **{ $max_turns } turns** for current goal.
goal_status_queued = Queued
goal_status_label = Active
goal_status_paused = Paused
goal_status_pending_approval = Pending Approval
goal_status_budget_limited = Budget Limited
goal_status_complete = Complete
goal_status_cancelled = Cancelled
goal_status_needs_review = Needs Review
goal_status_header = **Goal:** { $objective }
goal_status_line = **Status:** { $status }
goal_budget_tokens = Tokens: { $used }/{ $max }
goal_budget_turns = Turns: { $used }/{ $max }
goal_budget_header = **Budget:** { $parts }
usage_subgoal_add = Usage: `/subgoal add <text>`
subgoal_added = Subgoal added: **{ $text }**
no_subgoals_defined = No subgoals defined for the current goal.
current_subgoals = **Current Subgoals:**
usage_subgoal_remove = Usage: `/subgoal remove <index>`
subgoal_removed = Subgoal removed: **{ $text }**
subgoal_index_out_of_range = Subgoal index { $index } out of range.
cleared_subgoals = Cleared { $count } subgoals.
no_active_goal_constraint = No goal found. Set a goal first with `/goal <objective>`.
no_constraints_set = No constraints set for the current goal.
goal_constraint_added = Constraint added: **{ $constraint }**
goal_constraints_cleared = All constraints cleared.
goal_status_constraints = **Constraints:** { $items }
goal_status_criteria = **Acceptance Criteria:** { $items }
goal_status_subgoals = **Subgoals:** { $items }
no_goal_to_resume = No goal to resume.
goal_already_active = Goal is already active.
no_goal_to_clear = No goal to clear.
no_active_goal_to_clear = No active goal to clear.
no_active_goal_set_first = No active goal. Set a goal first with `/goal <objective>`.
no_active_goal_budget = No active goal to set budget for.
usage_goal_budget = Usage: `/goal budget <max_turns>` — e.g. `/goal budget 10`
budget_at_least_one = Budget must be at least 1.
invalid_budget = Invalid budget value. Use a number, e.g. `/goal budget 10`
background_tasks_not_available = Background tasks are not available.
usage_btw = Usage: `/btw <task>` | `/btw list` | `/btw cancel <id>` | `/btw steer <id> <instruction>`
background_none = No background tasks.
background_header = **Background Tasks**
background_cancel_usage = Usage: `/btw cancel <task_id>`
background_steer_usage = Usage: `/btw steer <task_id> <instruction>`
background_cancelled = Task `{ $task_id }` cancelled.
background_not_found = Task `{ $task_id }` not found or already finished.
background_steer_ok = Steering applied to `{ $task_id }`.
background_steer_fail = Task `{ $task_id }` not found or already finished.
background_started =
    Background task started: `{ $task_id }`
    I'll notify you when it's done.
background_completed =
    ✅ Background task completed: "{ $title }"
    { $result }
background_failed =
    ❌ Background task failed: "{ $title }"
    { $result }
bash_bg_finish_title = Background task finished
bash_bg_finish_success =
    Background task completed (pid={ $pid }).
    Command: { $command }
bash_bg_finish_with_error =
    Background task ended with { $error_category } (pid={ $pid }, status={ $status }, exit_code={ $exit_code }).
    Command: { $command }
bash_bg_finish_generic =
    Background task { $status } (pid={ $pid }, exit_code={ $exit_code }).
    Command: { $command }
new_session_started =  New conversation started. Your next message begins a fresh session.
compact_not_configured = ℹ Compaction not configured.
compact_success =  Context compacted: { $message_count } messages summarized, ~{ $tokens_saved } tokens saved.{ $topic_hint }
compact_skipped = ℹ Compaction skipped: { $reason }
compact_failed =  Compaction failed: { $error }
retry_not_configured = ℹ Retry not configured.
retry_nothing = ℹ Nothing to retry.
retry_failed = ℹ Retry failed.
retry_failed_error =  Retry failed: { $error }
undo_not_configured = ℹ Undo not configured.
undo_nothing = ℹ Nothing to undo.
undo_failed = ℹ Undo failed.
undo_failed_error =  Undo failed: { $error }
undo_success = ↩ Undone: { $count } message(s) removed.
undo_reverted = ↩ Reverted { $count } file(s).
topic_not_configured = ℹ Topic management is not configured.
topic_bound =
     { $scope } bound{ $agent_label }.
    Use /unbind to remove.
topic_unbound =  { $scope } unbound.
topic_no_binding = ℹ No binding found for this { $scope }.
topic_status =
     { $scope } Status
    { $agent_label }
    Status: { $status }{ $bound_label }
topic_no_binding_defaults =  No binding for this { $scope } (using defaults).
topic_command_failed =  { $scope } command failed: { $error }
topic_scope_topic = Topic
topic_scope_channel = Channel
topic_agent_switched =  (agent: { $from_agent } → { $to_agent })
topic_agent_only =  (agent: { $agent_id })
topic_status_agent = Agent: { $agent_id }
topic_status_agent_default = Agent: default
topic_status_bound_at =
    
    Bound: { $bound_at }
topic_status_enabled = enabled
topic_status_disabled = disabled
yolo_off =  YOLO mode is **OFF** - tool approvals required
yolo_on_expires =  YOLO mode is **ON** - expires in { $seconds }s
yolo_off_expired =  YOLO mode is **OFF** (expired)
yolo_on_no_expiration =  YOLO mode is **ON** (no expiration)
yolo_disabled =  YOLO mode **disabled** - tool approvals re-enabled
yolo_activated =
     **YOLO mode activated** - all tool calls will auto-approve
    
     **Warning**: This bypasses all security checks. Use with caution!
yolo_activated_timeout =
     **YOLO mode activated** - expires in { $timeout }s
    
     **Warning**: All tool calls will auto-approve. Use with caution!
yolo_already_off = ℹ YOLO mode was already OFF
yolo_invalid =  Invalid YOLO action. Use: /yolo [on|off|toggle|status]
yolo_invalid_usage =  Invalid /yolo command. Use: `/yolo [on|off|toggle|status] [timeout_seconds]`
personality_header =  **Available Personality Styles**:
personality_list_fallback =  Available styles:
personality_current =
    
    
     Current session style: **{ $style }**
personality_reset =  Personality reset to **Professional** (default)
personality_activated =
    { $emoji } **{ $name }** activated!
    
    { $description }
personality_set =  Personality set to **{ $style }**
personality_invalid =  Invalid style '{ $style }'. Use `/personality list` to see available options.
status_header = **Session Status**
status_session = • **Session:** `{ $session_id }`
status_title = • **Title:** { $title }
status_created = • **Created:** { $created_at }
status_last_activity = • **Last Activity:** { $last_activity }
status_model = • **Model:** { $model_name }
status_tokens = • **Tokens:** { $total_tokens }
status_cost = • **Cost:** ${ $total_usd }
status_calls = • **Calls:** { $total_calls }
status_no_session = • No active session
status_budget_header = 📊 **Channel Budget**
status_budget_today = • Today: ${ $today_cost } / ${ $daily_limit } ({ $usage_pct }%)
status_agent_running = • **Agent:** Running
status_agent_idle = • **Agent:** Idle
status_queued = • **Queued:** { $count }
status_yolo_on = • **YOLO:** ON
status_yolo_expires = • **YOLO:** ON (expires { $seconds }s)
help_header =  **Available Commands**
skill_not_configured = ℹ Skill command /{ $cmd } is not configured.
skill_load_failed =  Failed to load skill for /{ $cmd }.
pairing_pending = Your access request is pending approval.
pairing_submitted = Your access request has been submitted. An admin will review it soon.
mute_confirm = Muted. I will only respond when mentioned now.
search_not_configured = This agent requires web search, but no search service is configured. Please set up a search service in Settings first.
search_unreachable = Search service is configured but currently unreachable. Please check your search service and ensure it is running, then try again.
daily_budget_blocked = Daily budget limit reached. Execution was blocked. Adjust your budget limit in the Web Settings app, then try again.
channel_budget_blocked = This channel's daily budget has been reached. Other channels and Web sessions are not affected. The channel owner can adjust the limit in Settings > Budget.
cooldown_retry =
    
    
    ⏱️ Please retry in {seconds:.0f} seconds.
config_next_steps =
    
    
    Next steps:
    { $steps }
component_options_prefix = Options
component_quick_reply_instruction = ↩ Reply with a number to select
placeholder_thinking =  Thinking...
placeholder_no_response =  No response generated.
draft_review_pending = ✏️ Reply drafted — awaiting review before sending.
draft_review_reason = AI-generated reply requires review before sending to channel.
placeholder_execution_error =  Error: { $error }
placeholder_request_timeout =  Request timed out.
placeholder_retrying =
    
    
    [Retrying... { $attempt }/{ $max_retries }]
error_rate_limit = API rate limit reached — the model couldn't generate a response. Please try again in a moment.
error_overloaded = The AI service is temporarily overloaded. Please try again in a moment.
error_billing = Service temporarily unavailable due to a configuration issue. Please contact the administrator.
error_auth = Service temporarily unavailable due to a configuration issue. Please contact the administrator.
error_timeout = The request timed out. Please try again.
error_context_overflow = The conversation is too long. Please start a new session.
error_format = The AI generated an invalid format. Please try again.
error_model_not_found = The requested model is not available. Please select a different model.
error_safety_block = The request was blocked by safety filters.
error_response_format = The AI generated an invalid format. Please try again.
error_unknown = Something went wrong while processing your request. Please try again later.
cmd_stop = Stop the currently running agent task
cmd_new = Start a new conversation session
cmd_compact = Compress conversation context to reduce token cost
cmd_retry = Retry the last message
cmd_undo = Remove the last user/assistant exchange
cmd_yolo = Toggle YOLO mode (skip tool approval prompts)
cmd_personality = Switch session personality style
cmd_bind = Bind an agent to this topic or channel
cmd_unbind = Unbind agent from this topic or channel
cmd_topic = Show current topic/channel binding status
cmd_goal = Set, manage, or check a persistent cross-turn goal
cmd_subgoal = Dynamically add/remove/list subgoals for the running goal
cmd_steer = Redirect the running agent mid-execution with a new instruction
cmd_queue = Queue a task to run after the current agent task completes
cmd_background = Run a task in a separate background session without blocking the current conversation
cmd_status = Show current session status (tokens, cost, model, agent state)
cmd_help = Show available commands
cat_Session = Session
cat_Configuration = Configuration
cat_Topic = Topic
cat_Goals = Goals
cat_Execution = Execution
cat_Info = Info
cmd_handoff = Transfer this conversation to another platform/channel
usage_handoff = Usage: `/handoff <target_channel>`
handoff_success =
     Conversation transferred to **{ $target }**.
    You can continue this conversation on { $target } now.
handoff_no_target = Please specify a target channel. Use `/handoff <target_channel>`.
handoff_channel_not_found = Channel `{ $target }` not found or not connected.
handoff_no_pairing = No user pairing found for `{ $target }`. Please send a message in that channel first to establish a connection.
handoff_same_channel = Already on this channel — no transfer needed.
handoff_failed = Handoff failed: { $error }
help_alias =  (alias: { $aliases })
kanban_not_available = Kanban task management is not available.
kanban_usage =
    📋 **Kanban Commands:**
    `/kanban list` — list tasks
    `/kanban show <id>` — task details
    `/kanban create <title>` — create task
    `/kanban comment <id> <msg>` — add comment
    `/kanban edit <id> title|desc <text>` — edit task
    `/kanban complete <id>` — mark done
    `/kanban block <id> [reason]` — block
    `/kanban unblock <id>` — unblock
    `/kanban archive <id>` — archive
    `/kanban stats` — board statistics
kanban_error = ❌ Kanban command failed. Please check the syntax and try again.
session_reset_notify_idle = ℹ️ Session auto-reset: no activity for { $minutes } minutes. This is a fresh conversation.
session_reset_notify_daily = ℹ️ Session auto-reset: daily reset at { $hour }:00 UTC. This is a fresh conversation.
memory_unavailable = ℹ Memory system is unavailable.
memory_no_pending = ℹ No pending memories to review.
memory_pending_header = 📋 **Pending Memories** ({ $count }):
memory_pending_hint = Use `/memory approve <id>` or `/memory reject <id>` to review, or `/memory approve all` to approve all.
memory_approved = ✅ Memory `{ $id }` approved.
memory_rejected = ❌ Memory `{ $id }` rejected.
memory_approved_all = ✅ Approved { $count } pending memories.
memory_not_found = ℹ No pending memory matching `{ $id }`.
memory_error = ❌ Memory command failed. Please try again.
cmd_memory = Review pending memory writes (approve/reject)
cmd_learn = Teach the agent a new skill from a URL, file, or conversation
cat_Memory = Memory
cat_Skills = Skills
learn_not_configured = ℹ Skill learning is not configured in this environment.
learn_failed = ❌ Failed to build the learning prompt. Please try again.
reassurance_still_running = ⚓ Still working… ({ $steps } steps done{ $stage }) — hang tight!
agent_picker_no_agents = No agents configured.
agent_picker_select = Select an agent:
agent_picker_switched = Switched to: { $name }
artifact_deep_link = 💻 View interactive page
artifact_deep_link_named = 💻 { $filename }
