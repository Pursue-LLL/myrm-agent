# services/skills 模块架构

## 架构概述

技能成长相关服务层。按业务域收敛为两个子包：`evolution_review/`（审核域）与 `growth/`（成长域）；根目录保留独立门面文件（账本、草稿通知、权限、语义去重、事件、WebSocket 等）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `desktop_recording/` | 子域 | 桌面工作流录制：会话注册表（保留上限 + 并发采集预算）与采集循环生命周期（清单见 [`desktop_recording/_ARCH.md`](desktop_recording/_ARCH.md)） | — |
| `evolution_review/` | 子域 | Evolution 审核：类型 + 持久化 + 查询 + 写操作 + 落盘编排（清单见 [`evolution_review/_ARCH.md`](evolution_review/_ARCH.md)） | — |
| `nightly_review/` | 子域 | 夜间体检：协作评分 + 不再犯盯梢验收 + 早晨 digest（清单见 [`nightly_review/_ARCH.md`](nightly_review/_ARCH.md)） | — |
| `growth/` | 子域 | 技能成长：动作 SSOT + case DTO + case 查询 + 账本审计/投影 + 生命周期编排（清单见 [`growth/_ARCH.md`](growth/_ARCH.md)） | — |
| `solidify/` | 子域 | 交付物固化为全包 Skill：参数最小化提取 + 4合1资产打包 + 外部真机预览（清单见 [`solidify/_ARCH.md`](solidify/_ARCH.md)） | — |
| `evolution_reviews.py` | 门面 | evolution 审核生命周期门面（re-export `evolution_review/` 公共 API） | ✅ |
| `experience_ledger.py` | 核心 | 学习资产事件账本（append-only，统一记录 migration/evolution/review/skill_growth 事件，并提供技能成长聚合查询） | ✅ |
| `draft_notification.py` | 核心 | 技能成长记录持久化 + 安全预检（CRITICAL 硬拦截）+ 24h 去重 + 草稿 payload 携带结构化的 `reason_code`（`REASON_*`：`risk:` / `similar:` / `scan_failed` / `evolution_locked` / `apply_failed`）/ `security_scan_summary` / `apply_error`，审核备注从不写进会成为 SKILL.md `description` 的字段，由卡片按原因码本地化 + `ApprovalRecord` rich status 落库 + `SKILL_GROWTH_UPDATED` 事件发布单一出口 + `NEW_SKILL_DRAFT` 事件发布 + ledger 镜像 | ✅ |
| `auto_extractor.py` | 核心 | 技能物化辅助器。执行 Python AST 语法门禁，将已通过策略判断的新技能安全落盘（补丁一律走人工审核，这里直接拒绝），并发布 `notify=False` 的 `SKILL_EVOLVED` 事件，提示由成长事件承担，避免同一次学习弹两条；`render_skill_draft_markdown` 渲染新技能落盘文本，安全预检与物化共用；description 经 `yaml_scalar` 引号转义，缺失时回退 trigger_condition 再回退技能名，不写占位文案 | ✅ |
| `permission_service.py` | 核心 | 技能权限管理服务：per-session 缓存、授权加载、卸载时清除授权/审计数据 | ✅ |
| `similarity_checker.py` | 核心 | 技能语义去重实现。基于 HybridSkillSearchEngine 检查新技能是否与已有技能功能重复，防止技能熵增 | ✅ |
| `evolution_events.py` | 辅助 | 技能进化 `SKILL_EVOLVED` 事件发布（services 层单一入口）；`notify=False` 时界面只刷新、不弹 toast | ✅ |
| `scan_risk_policy.py` | 核心 | 后台自动学习的"高危新增 → 人工复核"共用策略：对比原内容与新内容的扫描结果，按 (类别, 描述, 严重度) 计数差分判定是否新增 HIGH+ 风险（语境型类别只对 CRITICAL 生效，新技能对比空内容）；扫描失败 fail-closed；复盘新技能入口（`growth/lifecycle.py`）与进化审批流（`confidence_approval_flow.py`）共用，信号词汇 `new_high_finding:<类别>` / `scan_unavailable` 由审核卡片本地化 | ✅ |
| `write_orchestrator.py` | 核心 | SKILL.md 写入 SSOT：DB 版本 persist 与磁盘 `sync_disk` 同序；meta-tool 失败时 `restore_skill_md_from_active_version` | ✅ |
| `package_revision_service.py` | 核心 | PackageRevision 持久化与 fail-closed 恢复 | ✅ |
| `mutation_batch_hook.py` | 核心 | skill_manage 批次提交后 batch_snapshots 单事务写入（fail-closed）；落库提交后经工具进度通道向流广播批次 id（广播失败只记 WARNING，不影响已提交批次） | ✅ |
| `mutation_batch_stream.py` | 核心 | 批次提交事件契约：hook 产出 `tool_end` 事件（`skill_manage_tool` + `skill_mutation_batch_id`），`stream_collector`（及前端 `skillManageBatchLink.ts`）把批次 id 关联到仍在等待批次的最新 skill_manage 步骤（harness 只流式输出调用参数、不含工具结果，步骤本身读不到批次 id；并发多个 skill_manage 调用时按“最新未关联步骤”配对） | ✅ |
| `skill_manage_batch_parse.py` | 核心 | 解析 `myrm_skill_batch:` JSON 与 legacy batch_id 文本，供 stream_collector | ✅ |
| `mutation_batch_service.py` | 核心 | 批次回滚 + 成功后 consume 快照 + compensation / batch_already_consumed；批次内新建的本地 skill 经 `skill_creation_service` 回收（skill store 拒绝删除 LOCAL，且仅回收其存储根内的目录）。读完快照行即 `session.rollback()` 结束请求会话的读事务：恢复经其它 session 提交版本行，仍持旧读快照的会话会在末尾 DELETE 以 `SQLITE_BUSY_SNAPSHOT`（`database is locked`，busy_timeout 不覆盖）失败，表现为文件已恢复却返回 503；因此消费快照的 DELETE 开新事务（纯写首语句，走 `BEGIN IMMEDIATE`）。`batch_rollback_lock(batch_id)` 让同一批次的撤销请求串行（路由在锁内完成回滚与 commit）：两个标签页同时撤销时，后到者在先到者提交前就捕获了现场，随后因 skill 已被移除而失败，并把过期现场回写成该已移除 skill 的版本、回 409 `rollback_failed`；串行后后到者读到已消费的快照，回 `batch_already_consumed`。回归测试在真实 WAL 文件库上跑（`tests/services/skills/test_mutation_batch_rollback_transaction.py`），内存库共享单连接无法复现 | ✅ |

## 设计原则

- **按域收敛**：多文件业务域必须收进以域命名的子目录（`evolution_review/`、`growth/`），根目录只保留单文件门面与独立域模块；子包内部跨模块引用用相对导入，跨子域引用用 `..` 相对导入。
- **禁止聚合导出**：子包 `__init__.py` 不做聚合（`experience_ledger → growth.* → evolution_reviews → evolution_review.types → experience_ledger` 条件性依赖环——仅当两包同时聚合导出时才构成循环导入），外部一律穿透导入子模块；公共 API 由 `evolution_reviews.py` 门面统一 re-export。
