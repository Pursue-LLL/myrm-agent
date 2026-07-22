mobile_hitl_open = モバイルで承認を開く
mobile_btw_open = モバイルで結果を確認
web_continue_chat = ブラウザで続ける

no_active_task_to_stop = ℹ 停止するアクティブなタスクがありません。
execution_stopped =  実行を停止しました。
placeholder_stopped =  実行を停止しました。
no_pending_approval = ℹ 保留中の承認リクエストはありません。
approval_processing =  承認を処理中...
approval_always_processing =  承認を処理し、常時許可リストに追加中...
approval_denial_processing =  拒否を処理中...
approval_batch_processing =  { $approve_count } 件の承認、{ $reject_count } 件の拒否を処理中...
approval_batch_processing_always =  { $approve_count } 件の承認（{ $always_count } 件は常時許可）、{ $reject_count } 件の拒否を処理中...
approval_timeout_resolved = ℹ この承認はタイムアウトにより自動処理されました。操作不要です。
permission_denied =  権限不足：`/{ $cmd }` には管理者権限が必要です。
usage_steer = 使い方：`/steer <新しい指示>`
steering_applied = 指示を適用しました：_{ $preview }_
usage_queue = 使い方：`/queue <タスクの説明>`
queue_queued = キューに追加しました。現在のタスク完了後に実行されます。
queue_immediate = アクティブなタスクなし — 直ちに実行します。
goal_system_not_configured =  この環境ではゴールシステムが設定されていません。
goal_management_not_available = ゴール管理は利用できません。
agent_is_running_goal = Agent は実行中です — 実行中は /goal status、/goal pause、/goal clear をご利用ください。新しいゴールを設定する前に /stop で Agent を停止してください。
usage_goal = 使い方：`/goal <目標>`
goal_set =
    ゴールを設定しました：**{ $goal }**
    Agent がこれから作業を開始します。
goal_queued =
    ゴールをキューに追加しました：**{ $goal }**
    現在のゴール完了後に自動的に開始されます。
goal_active_exists =
    アクティブなゴールがあります：**{ $objective }**
    先に `/goal clear` を使用するか、`/goal status` で進捗を確認してください。
no_goal_is_set = ゴールが設定されていません。`/goal <目標>` で設定してください。
no_active_goal_to_pause = 一時停止するアクティブなゴールがありません。
no_active_goal_session = アクティブなゴールセッションが見つかりません。
no_active_goal_subgoals = サブゴールを管理するアクティブなゴールがありません。
goal_paused =
    ゴールを一時停止しました：**{ $objective }**
    `/goal resume` で再開できます。
goal_wait =
    ゴール待機中：**{ $objective }**
    理由：{ $reason }
    `/goal unwait` で再開できます。
goal_unwait = ゴールを待機状態から再開しました：**{ $objective }**
goal_not_waiting = ゴールは待機状態ではありません。
goal_wait_not_supported = この環境では待機モードはサポートされていません。
goal_resumed = ゴールを再開しました：**{ $objective }**
goal_cleared = ゴールをクリアしました：**{ $objective }**
goal_cannot_resume = 「{ $status }」状態のゴールは再開できません。
goal_budget_set = 現在のゴールの予算を **{ $max_turns } ターン** に設定しました。
goal_status_queued = キュー待ち
goal_status_label = 実行中
goal_status_paused = 一時停止
goal_status_pending_approval = 承認待ち
goal_status_budget_limited = 予算制限
goal_status_wait = 待機中
goal_status_complete = 完了
goal_status_cancelled = キャンセル済み
goal_status_needs_review = レビュー待ち
goal_status_header = **ゴール：** { $objective }
goal_status_line = **ステータス：** { $status }
goal_budget_tokens = トークン：{ $used }/{ $max }
goal_budget_turns = ターン数：{ $used }/{ $max }
goal_budget_header = **予算：** { $parts }
usage_subgoal_add = 使い方：`/subgoal add <テキスト>`
subgoal_added = サブゴールを追加しました：**{ $text }**
no_subgoals_defined = 現在のゴールにサブゴールは定義されていません。
current_subgoals = **現在のサブゴール：**
usage_subgoal_remove = 使い方：`/subgoal remove <インデックス>`
subgoal_removed = サブゴールを削除しました：**{ $text }**
subgoal_index_out_of_range = サブゴールインデックス { $index } は範囲外です。
cleared_subgoals = { $count } 個のサブゴールをクリアしました。
no_active_goal_constraint = ゴールが見つかりません。先に `/goal <目標>` でゴールを設定してください。
no_constraints_set = 現在のゴールに制約は設定されていません。
goal_constraint_added = 制約を追加しました：**{ $constraint }**
goal_constraints_cleared = すべての制約をクリアしました。
goal_status_constraints = **制約：** { $items }
goal_status_criteria = **受け入れ基準：** { $items }
goal_status_subgoals = **サブゴール：** { $items }
no_goal_to_resume = 再開するゴールがありません。
goal_already_active = ゴールは既にアクティブです。
no_goal_to_clear = クリアするゴールがありません。
no_active_goal_to_clear = クリアするアクティブなゴールがありません。
no_active_goal_set_first = アクティブなゴールがありません。先に `/goal <目標>` でゴールを設定してください。
no_active_goal_budget = 予算を設定するアクティブなゴールがありません。
usage_goal_budget = 使い方：`/goal budget <最大ターン数>` — 例：`/goal budget 10`
budget_at_least_one = 予算は 1 以上で指定してください。
invalid_budget = 無効な予算値です。数値を指定してください。例：`/goal budget 10`
background_tasks_not_available = バックグラウンドタスクは利用できません。
usage_btw = 使い方：`/btw <タスク>` | `/btw list` | `/btw cancel <id>` | `/btw steer <id> <指示>`
background_none = バックグラウンドタスクはありません。
background_header = **バックグラウンドタスク**
background_cancel_usage = 使い方：`/btw cancel <task_id>`
background_steer_usage = 使い方：`/btw steer <task_id> <指示>`
background_cancelled = タスク `{ $task_id }` をキャンセルしました。
background_not_found = タスク `{ $task_id }` が見つからないか、既に終了しています。
background_steer_ok = `{ $task_id }` に指示を適用しました。
background_steer_fail = タスク `{ $task_id }` が見つからないか、既に終了しています。
background_started =
    バックグラウンドタスクを開始しました：`{ $task_id }`
    完了したらお知らせします。
background_completed =
    ✅ バックグラウンドタスク完了："{ $title }"
    { $result }
background_failed =
    ❌ バックグラウンドタスク失敗："{ $title }"
    { $result }
bash_bg_finish_title = バックグラウンドタスク完了
bash_bg_finish_success =
    バックグラウンドタスクが完了しました (pid={ $pid })。
    コマンド：{ $command }
bash_bg_finish_with_error =
    バックグラウンドタスクが異常終了しました：{ $error_category } (pid={ $pid }, status={ $status }, exit_code={ $exit_code })。
    コマンド：{ $command }
bash_bg_finish_generic =
    バックグラウンドタスク { $status } (pid={ $pid }, exit_code={ $exit_code })。
    コマンド：{ $command }
goal_stream_failed_title = ゴールの確認が必要です
goal_stream_failed_message =
    自律タスクが予期せず停止しました。ゴールパネルを開いて確認・続行してください。
new_session_started =  新しい会話を開始しました。次のメッセージから新しいセッションになります。
compact_not_configured = ℹ 圧縮が設定されていません。
compact_success =  コンテキストを圧縮しました：{ $message_count } メッセージを要約、約 { $tokens_saved } トークンを節約。{ $topic_hint }
compact_skipped = ℹ 圧縮をスキップしました：{ $reason }
compact_failed =  圧縮に失敗しました：{ $error }
retry_not_configured = ℹ リトライが設定されていません。
retry_nothing = ℹ リトライするものがありません。
retry_failed = ℹ リトライに失敗しました。
retry_failed_error =  リトライに失敗しました：{ $error }
undo_not_configured = ℹ 取り消しが設定されていません。
undo_nothing = ℹ 取り消すものがありません。
undo_failed = ℹ 取り消しに失敗しました。
undo_failed_error =  取り消しに失敗しました：{ $error }
undo_success = ↩ 取り消しました：{ $count } メッセージを削除しました。
undo_reverted = ↩ { $count } ファイルを元に戻しました。
topic_not_configured = ℹ トピック管理が設定されていません。
topic_bound =
     { $scope } をバインドしました{ $agent_label }。
    /unbind で解除できます。
topic_unbound =  { $scope } のバインドを解除しました。
topic_no_binding = ℹ この { $scope } にバインドはありません。
topic_status =
     { $scope } ステータス
    { $agent_label }
    ステータス：{ $status }{ $bound_label }
topic_no_binding_defaults =  この { $scope } にバインドはありません（デフォルト設定を使用中）。
topic_command_failed =  { $scope } コマンドが失敗しました：{ $error }
topic_scope_topic = トピック
topic_scope_channel = チャンネル
topic_agent_switched = （エージェント：{ $from_agent } → { $to_agent }）
topic_agent_only = （エージェント：{ $agent_id }）
topic_status_agent = エージェント：{ $agent_id }
topic_status_agent_default = エージェント：デフォルト
topic_status_bound_at =
    
    バインド日時：{ $bound_at }
topic_status_enabled = 有効
topic_status_disabled = 無効
yolo_off =  YOLO モードは **オフ** — ツール実行に承認が必要です
yolo_on_expires =  YOLO モードは **オン** — { $seconds } 秒後に期限切れ
yolo_off_expired =  YOLO モードは **オフ**（期限切れ）
yolo_on_no_expiration =  YOLO モードは **オン**（期限なし）
yolo_disabled =  YOLO モード **無効化** — ツール承認が復元されました
yolo_activated =
     **YOLO モードを有効化しました** — すべてのツール呼び出しが自動承認されます
    
     **警告**：すべてのセキュリティチェックがバイパスされます。慎重にご利用ください！
yolo_activated_timeout =
     **YOLO モードを有効化しました** — { $timeout } 秒後に期限切れ
    
     **警告**：すべてのツール呼び出しが自動承認されます。慎重にご利用ください！
yolo_already_off = ℹ YOLO モードは既にオフです
yolo_invalid =  無効な YOLO 操作です。使い方：/yolo [on|off|toggle|status]
yolo_invalid_usage =  無効な /yolo コマンドです。使い方：`/yolo [on|off|toggle|status] [timeout_seconds]`
personality_header =  **利用可能なパーソナリティスタイル**：
personality_list_fallback =  利用可能なスタイル：
personality_current =
    
    
     現在のセッションスタイル：**{ $style }**
personality_reset =  パーソナリティを **Professional**（デフォルト）にリセットしました
personality_activated =
    { $emoji } **{ $name }** を有効化しました！
    
    { $description }
personality_set =  パーソナリティを **{ $style }** に設定しました
personality_invalid =  無効なスタイル「{ $style }」。`/personality list` で利用可能なオプションを確認してください。
status_header = **セッションステータス**
status_session = • **セッション：** `{ $session_id }`
status_title = • **タイトル：** { $title }
status_created = • **作成日時：** { $created_at }
status_last_activity = • **最終アクティビティ：** { $last_activity }
status_model = • **モデル：** { $model_name }
status_tokens = • **トークン：** { $total_tokens }
status_cost = • **コスト：** ${ $total_usd }
status_calls = • **呼び出し回数：** { $total_calls }
status_no_session = • アクティブなセッションがありません
status_budget_header = 📊 **チャンネル予算**
status_budget_today = • 本日：${ $today_cost } / ${ $daily_limit }（{ $usage_pct }%）
status_agent_running = • **Agent：** 実行中
status_agent_idle = • **Agent：** 待機中
status_queued = • **キュー：** { $count }
status_yolo_on = • **YOLO：** オン
status_yolo_expires = • **YOLO：** オン（{ $seconds } 秒後に期限切れ）
help_header =  **利用可能なコマンド**
skill_not_configured = ℹ スキルコマンド /{ $cmd } が設定されていません。
skill_load_failed =  /{ $cmd } のスキルの読み込みに失敗しました。
pairing_pending = アクセスリクエストは管理者の承認待ちです。
pairing_submitted = アクセスリクエストを送信しました。管理者が近日中に審査します。
mute_confirm = ミュートしました。今後はメンション時のみ応答します。
search_not_configured = このエージェントにはウェブ検索が必要ですが、検索サービスが設定されていません。先に設定で検索サービスを追加・有効化してください。
search_unreachable = 検索サービスは設定されていますが、現在接続できません。検索サービスが正常に動作しているか確認してから再試行してください。
daily_budget_blocked = 日次予算の上限に達しました。実行がブロックされました。Web 設定で予算上限を調整してから再試行してください。
channel_budget_blocked = このチャンネルの日次予算に達しました。他のチャンネルや Web セッションには影響しません。チャンネルオーナーが設定 > 予算で上限を調整できます。
cooldown_retry =
    
    
    ⏱️ {seconds:.0f} 秒後にリトライしてください。
config_next_steps =
    
    
    次のステップ：
    { $steps }
component_options_prefix = オプション
component_quick_reply_instruction = ↩ 番号を入力して選択
placeholder_thinking =  考え中...
placeholder_no_response =  応答が生成されませんでした。
draft_review_pending = ✏️ 返信の下書きが完了しました — 送信前にレビューをお待ちしています。
draft_review_reason = AI 生成の返信はチャンネルに送信する前にレビューが必要です。
placeholder_execution_error =  エラー：{ $error }
placeholder_request_timeout =  リクエストがタイムアウトしました。
placeholder_retrying =
    
    
    [リトライ中... { $attempt }/{ $max_retries }]
error_rate_limit = API レート制限に達しました — モデルが応答を生成できませんでした。しばらくしてから再試行してください。
error_overloaded = AI サービスが一時的に過負荷状態です。しばらくしてから再試行してください。
error_billing = 設定の問題によりサービスが一時的に利用できません。管理者にお問い合わせください。
error_auth = 設定の問題によりサービスが一時的に利用できません。管理者にお問い合わせください。
error_timeout = リクエストがタイムアウトしました。再試行してください。
error_context_overflow = 会話が長すぎます。新しいセッションを開始してください。
error_format = AI が無効なフォーマットを生成しました。再試行してください。
error_model_not_found = リクエストされたモデルは利用できません。別のモデルを選択してください。
error_safety_block = リクエストがセーフティフィルターによりブロックされました。
error_response_format = AI が無効なフォーマットを生成しました。再試行してください。
error_unknown = リクエストの処理中に問題が発生しました。しばらくしてから再試行してください。
cmd_stop = 実行中の Agent タスクを停止
cmd_new = 新しい会話セッションを開始
cmd_compact = 会話コンテキストを圧縮してトークンコストを削減
cmd_retry = 最後のメッセージをリトライ
cmd_undo = 最後のユーザー/アシスタントの対話を削除
cmd_yolo = YOLO モードを切り替え（ツール承認をスキップ）
cmd_personality = セッションのパーソナリティスタイルを切り替え
cmd_bind = エージェントをこのトピックまたはチャンネルにバインド
cmd_unbind = このトピック/チャンネルからエージェントのバインドを解除
cmd_topic = 現在のトピック/チャンネルのバインド状態を表示
cmd_goal = ターンをまたぐ持続的なゴールを設定・管理・確認
cmd_subgoal = 実行中のゴールのサブゴールを動的に追加/削除/一覧表示
cmd_steer = 実行中の Agent に新しい指示を注入して方向修正
cmd_queue = 現在のタスク完了後に実行するタスクをキューに追加
cmd_background = 現在の会話をブロックせずに別のバックグラウンドセッションでタスクを実行
cmd_status = 現在のセッション状態を表示（トークン、コスト、モデル、Agent 状態）
cmd_help = 利用可能なコマンドを表示
cat_Session = セッション
cat_Configuration = 設定
cat_Topic = トピック
cat_Goals = ゴール
cat_Execution = 実行
cat_Info = 情報
cmd_handoff = この会話を他のプラットフォーム/チャンネルに転送
usage_handoff = 使い方：`/handoff <対象チャンネル>`
handoff_success =
     会話を **{ $target }** に転送しました。
    { $target } でこの会話を続けることができます。
handoff_no_target = 対象チャンネルを指定してください。使い方：`/handoff <対象チャンネル>`
handoff_channel_not_found = チャンネル `{ $target }` が見つからないか、接続されていません。
handoff_no_pairing = `{ $target }` でユーザーペアリングが見つかりません。先にそのチャンネルでメッセージを送信して接続を確立してください。
handoff_same_channel = 既にこのチャンネルにいます — 転送は不要です。
handoff_failed = ハンドオフに失敗しました：{ $error }
help_alias = （エイリアス：{ $aliases }）
kanban_not_available = カンバンタスク管理は利用できません。
kanban_usage =
    📋 **カンバンコマンド：**
    `/kanban list` — タスク一覧
    `/kanban show <id>` — タスク詳細
    `/kanban create <タイトル>` — タスク作成
    `/kanban comment <id> <メッセージ>` — コメント追加
    `/kanban edit <id> title|desc <テキスト>` — タスク編集
    `/kanban complete <id>` — 完了にする
    `/kanban block <id> [理由]` — ブロック
    `/kanban unblock <id>` — ブロック解除
    `/kanban archive <id>` — アーカイブ
    `/kanban stats` — ボード統計
kanban_error = ❌ カンバンコマンドが失敗しました。構文を確認して再試行してください。
session_reset_notify_idle = ℹ️ セッションを自動リセットしました：{ $minutes } 分間無操作。新しい会話です。
session_reset_notify_daily = ℹ️ セッションを自動リセットしました：毎日 { $hour }:00 UTC 定時リセット。新しい会話です。
memory_unavailable = ℹ メモリシステムは利用できません。
memory_no_pending = ℹ 保留中のメモリはありません。
memory_pending_header = 📋 **保留中のメモリ** ({ $count })：
memory_pending_hint = `/memory approve <id>` または `/memory reject <id>` でレビューするか、`/memory approve all` で一括承認できます。
memory_approved = ✅ メモリ `{ $id }` を承認しました。
memory_rejected = ❌ メモリ `{ $id }` を拒否しました。
memory_approved_all = ✅ { $count } 件の保留中メモリを承認しました。
memory_not_found = ℹ `{ $id }` に一致する保留中のメモリが見つかりません。
memory_error = ❌ メモリコマンドが失敗しました。再試行してください。
cmd_memory = 保留中のメモリ書き込みを確認（承認/拒否）
cmd_learn = URL、ファイル、または会話から Agent に新しいスキルを学習させる
cat_Memory = メモリ
cat_Skills = スキル
learn_not_configured = ℹ この環境ではスキル学習が設定されていません。
learn_failed = ❌ 学習プロンプトの構築に失敗しました。再試行してください。
reassurance_still_running = ⚓ 処理を続けています（{ $steps } ステップ完了{ $stage }）— お待ちください
agent_picker_no_agents = エージェントが設定されていません。
agent_picker_select = エージェントを選択してください：
agent_picker_switched = 切り替えました：{ $name }
artifact_deep_link = 💻 インタラクティブページを表示
artifact_deep_link_named = 💻 { $filename }
