# app/database/migrations 子包架构

数据库迁移子包：接入 Harness 层的 `StatefulMigrationEngine`，维护两条只追加的语句清单（`MIGRATION_STATEMENTS`、`INDEX_STATEMENTS`），一次性数据修复语句冻结在常量文件里。`app.database.migrations` 的导入路径与公开名字不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | ✅ 核心 | 迁移引擎集成与两条完整清单的出口。使用 Harness 层的 `StatefulMigrationEngine` 执行版本化 SQL 迁移，支持精准计时 (`duration_ms`)、基线平滑升级 (Baseline)、慢查询捕获和结构化失败报告；状态持久化在 `_schema_migrations` 和 `_schema_indexes` 表中。`MIGRATION_STATEMENTS` / `INDEX_STATEMENTS` 由各段按文件序号拼接，版本号即列表下标；`run_migrations` / `create_indexes` 执行两条清单；`has_pending_migrations` 只读判断 `_schema_migrations` 是否还缺版本（缺表或表里没有任何记录也算待执行），决定是否需要迁移前快照；`ensure_raw_sql_schema` 由 `create_indexes` 在末尾调用，保底创建不在 ORM 里的结构（`system_health_history`、`messages_fts` 与它的三个同步触发器、Conversation Recall 的表与 FTS5），因为库被基线化时迁移语句会被跳过；九条冻结常量原样再导出 | ✅ |
| `_sql_constants.py` | ✅ 核心 | 九条冻结的一次性数据修复 SQL，每条在 `MIGRATION_STATEMENTS` 里占一个位置；已执行的库按语句文本记校验和，所以文本字节不能变。`CLEAR_LEGACY_PROJECT_WORKSPACE_PATHS_SQL` 清空历史假工作区路径 `/persistent/workspace/project_%`（用户需通过 Mount Wizard 重新绑定）；`BACKFILL_LEGACY_WAKEUP_NOTICE_SQL` 给旧版没有标记的后台完成通知行（`wakeup_` 前缀）补 `followup` 标记，按主键范围扫描，已有标记的行不动；`REJECT_LEGACY_TOOL_STUCK_APPROVALS_SQL` 把遗留的循环守卫暂停（`action_type='tool_stuck'`）PENDING 审批行置为 REJECTED，这类行没有过期时间、会让所属聊天一直拒收新消息，只动该类型的 PENDING 行；`CLEAR_BUILTIN_SEARCH_MEMORY_POLICY_SQL` 清空快速 / 深度搜索两个预置体行里的记忆策略覆盖（它们跑默认策略），只动这两个 id，其余智能体的策略不变；`NORMALIZE_RETIRED_PROMPT_MODES_SQL` 把已退役的 `lean` / `naked` 提示词模式行改为 `full`（模式现在只有 `full` 与 `search`，由系统写入，不再由用户选择）；`REARM_STALLED_CRON_JOBS_SQL` 把启用却没有下一运行时刻的周期任务订为 1970 年到期，启动恢复发现它已过期后订下真实的下一时刻并记一次跳过，不补跑没人要求的运行，已有下一时刻的任务不动、第二遍不再有变化；`PAUSE_STALLED_ONCE_CRON_JOBS_SQL` 把同样停摆的一次性任务置为暂停，让所有者看到它需要新的时间；`STRIP_RETIRED_RESPONSE_LOCALE_POLICY_SQL` 与 `STRIP_RETIRED_RESPONSE_LOCALE_POLICY_FROM_SNAPSHOTS_SQL` 把智能体参数 `agents.engine_params` 与回滚快照 `agent_profile_snapshots` 里已退役的 `response_locale_policy` 键移除（没有其余参数的智能体存 NULL；参数为 NULL、不是合法 JSON 或没有该键的行不动，可重复执行；`agent_profile_history` 是只读记录，不动） | ✅ |
| `_migration_statements_1.py` | ✅ 核心 | `MIGRATION_STATEMENTS` 第 0 至 94 位（95 条），均已发布，不引用常量 | ✅ |
| `_migration_statements_2.py` | ✅ 核心 | 第 95 至 179 位（85 条），均已发布。开头是重建 `messages_fts` 的一组（删旧触发器与虚拟表，按 `content_rowid=rowid` 重建，再重建索引内容），之后有 `DROP TABLE IF EXISTS calendar_events` 与 `DROP TABLE IF EXISTS canvas`（`tests/architecture/test_calendar_schema_retired.py`、`test_canvas_schema_retired.py` 固定） | ✅ |
| `_migration_statements_3.py` | ✅ 核心 | 第 180 位起，是最后一段，新语句追加在这里。按位置引用 `_sql_constants.py` 的九条常量和 `personality_style_merge.py` 的 `MERGE_AGENT_PERSONALITY_STYLE_INTO_SYSTEM_PROMPT_SQL`（把自定义智能体已选的沟通风格文本追加进各自 `system_prompt`，预置体行不动，它们的提示词每次启动由规格重新同步），随后两条 `ALTER TABLE … DROP COLUMN personality_style` 删掉 `agents` 与 `agent_profile_history` 里的这一列；三条 `ALTER TABLE agents DROP COLUMN` 删掉职责范围 `responsibility_scope`、负责人标签 `owner_label`、验收标准 `acceptance_criteria`，两条 `ALTER TABLE cron_runs DROP COLUMN` 删掉运行记录的 `integrity_hash` 与 `prev_hash`，这五列都没有模型映射、也没有读写方；以上各条在列已不存在的库按幂等跳过 | ✅ |
| `_index_statements_1.py` | ✅ 核心 | `INDEX_STATEMENTS` 第 0 至 97 位（98 条），均已发布 | ✅ |
| `_index_statements_2.py` | ✅ 核心 | 第 98 位起，是最后一段，新语句追加在这里。除索引外含随索引一并演进的建表与改列语句：`ALTER TABLE interrupted_turn_markers DROP COLUMN pending_steering_messages` 删掉待回放转向消息列（没有模型映射、也没有读写方；列已不存在的库按幂等跳过），以及 `a2a_peers`、`procedural_rules`、`batch_image_jobs` 等退役表的 `DROP TABLE IF EXISTS` | ✅ |

## 追加规则

- 版本号就是语句在整条清单里的下标，账本表 `_schema_migrations` / `_schema_indexes` 按它记录，所以只在末尾追加，已发布的语句不删、不改、不挪位；`tests/database/test_migration_list_append_only.py` 按 SHA-256 固定了两条清单里已发布的语句。
- 新语句追加在最后一段（`_migration_statements_3.py`、`_index_statements_2.py`）的末尾；最后一段接近 400 行时新开下一个文件，并在 `__init__.py` 里按文件序号加入拼接。
- 运行函数留在 `__init__.py`，不放进单独的文件：测试按名字替换 `MIGRATION_STATEMENTS` / `INDEX_STATEMENTS`（`monkeypatch.setattr(migrations, …)`），运行函数必须在同一个模块里读取它们。
- 被测试按名字引用的一次性数据修复 SQL 写成常量放在 `_sql_constants.py`，清单里按位置引用同一个对象。
