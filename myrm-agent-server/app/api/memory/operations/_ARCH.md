# api/memory/operations/

## 架构概述

记忆运维 HTTP 层：指挥中心、Shared Context、归档恢复、诊断。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Memory operations submodule。聚合门面 re-export 顶层操作模块（archive_restore/backup/backup_remote/cognitive_clock_console/command_center/command_center_consolidation/command_center_diagnostics/conflicts/crud/domain_mesh/evidence_playback/external_transcripts/guardian/head_probe/import_rollback_preview/memory_graph/pending/radar/reindex/working_state）与 `shared_context/` 的 `shared_context_health`、`shared_context_history`、`shared_contexts`，供 memory router 单一入口导入 | ✅ |
| `archive_restore.py` | 模块 | 记忆归档恢复 API 操作层（`/archive/restore/*`）。只编排请求/响应和错误映射，恢复语义由服务层负责；只有 Memory Labs 的归档恢复弹窗调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载（归档导出 `/archive/export` 在 `crud.py`，对所有用户挂载）。 | ✅ |
| `backup.py` | 模块 | 本地备份 API：`/backup/create`、`/list`、`/restore`、`DELETE /{id}`。创建/恢复使用直接写入的 CRUD 管理器（恢复内容不得进入审批队列），列表/删除只碰持久卷；未知备份 404，快照不完整（含旧嵌入模型下仍有记忆未迁移）或备份损坏以 `success=false` + 可展示的原因返回 | ✅ |
| `backup_remote.py` | 模块 | 远程备份 API（WebDAV/S3 连接检测、立即备份、列表、合并恢复、删除、定时备份状态 `GET /auto-status`）；立即备份带稳定的 `error_code`（`snapshot`/`previous_model`/`upload`/`internal`/`busy`，界面据此显示本地化文案），成功时结束定时备份的失败期；列表读不到返回错误而不是空列表；备份/恢复同样使用直接写入的 CRUD 管理器 | ✅ |
| `cognitive_clock_console.py` | 模块 | 认知时钟控制台 API：`GET /guardian/cognitive-clock/status` 返回多频率时钟状态，`POST /guardian/cognitive-clock/trigger-t1` 手动触发 T1 会话防抖整合。只有 Memory Labs 的认知时钟面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载；策略解析复用 `guardian.resolve_guardian_policy`。 | ✅ |
| `command_center.py` | 模块 | 记忆指挥中心 API 操作层。将单用户/单沙箱记忆运行快照暴露给设置页 UI，只在 Memory Labs 开启时挂载（知识图谱与证据溯源分别由 `memory_graph.py`、`evidence_playback.py` 提供，对所有用户挂载），`GET /command-center` 支持可选 `project_id` 查询参数将快照聚焦到单个项目的 SharedContext 记忆空间；`GET /command-center/recall-boundary` 返回任务级审查优先召回边界与候选/生效分区快照。 | ✅ |
| `memory_graph.py` | 模块 | 记忆知识图谱 API：`GET /command-center/graph` 返回 Claim/Evidence 图的节点、边与按度数/冲突排序的核心主张（支持 namespace 过滤、时间点快照、是否含已取代关系）。对所有用户挂载，成长页（`/journey`）的知识图谱标签页读取它；路径前缀为 `/command-center`，不受 `MYRM_MEMORY_LABS` 控制。 | ✅ |
| `evidence_playback.py` | 模块 | 记忆证据溯源 API：`GET /command-center/evidence/playback` 返回证据徽标对应的脱敏会话切片或归档快照。对所有用户挂载，记忆卡片的证据抽屉读取它；路径前缀为 `/command-center`，不受 `MYRM_MEMORY_LABS` 控制。 | ✅ |
| `command_center_actions.py` | 模块 | 记忆指挥中心动作执行实现层。处理 GUI 治理动作（审批、拒绝、修正、Pin/Unpin、遗忘）；待审批记忆的批准/拒绝经审批队列统一审批入口（`services/memory/operations/pending_review.py`），编辑在审阅弹窗的 `edited_content` 完成。纪律默认一键恢复 `restore_disciplined_defaults` 归 Memory Doctor 修复执行器，不在本动作域。 | ✅ |
| `command_center_consolidation.py` | 模块 | 记忆合并回滚 API 操作层。将 Harness 层的 consolidation_rollback 逻辑暴露给设置页 UI。 | ✅ |
| `command_center_diagnostics.py` | 模块 | 记忆指挥中心诊断与修复 API 操作层。包含 Memory Doctor 历史基准趋势与结构化白名单修复。 | ✅ |
| `crud.py` | 模块 | Memory CRUD HTTP routes — thin transport layer. 导入回滚预演 `POST /import/rollback/dry-run` 由 `import_rollback_preview.py` 提供，其余导入/回滚路由（含实际回滚 `POST /import/rollback`）和归档导出 `/archive/export` 在这里。 | ✅ |
| `import_rollback_preview.py` | 模块 | 导入回滚预演 API：`POST /import/rollback/dry-run` 返回回滚一个已确认导入批次会撤销的内容安全预览。只有 Memory Labs 命令中心的导入回滚弹窗调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载；实际回滚 `POST /import/rollback` 不依赖预演，由 `crud.py` 提供并对所有用户挂载。 | ✅ |
| `external_transcripts.py` | 模块 | 外部 Agent 转录记忆召回 API。支持本地目录扫描增量建索与云端批量文件增量同步；同步服务经 `get_external_transcript_sync_service` 注入（可替换 watermark 存储） | ✅ |
| `head_probe.py` | 模块 | 记忆与会话头部探针：`GET /head` 返回 `MAX(seq)` 与变更状态，供轮询客户端、插件和后台同步任务在不做全量查询的情况下判断落后量；是登记的外部消费者接口，对所有用户挂载。 | ✅ |
| `guardian.py` | 模块 | 记忆守护者 API。`/overview` 单契约返回健康分、调度状态、守护策略（频率档位 + quiet window）、告警与晨间摘要（按最新完成维护窗口聚合）；手动维护触发支持 `safe/force` 契约；策略经 PUT 更新；健康/摘要读路径支持首访浏览器时区初始化，并在缺少客户端时区头时使用服务端本地时区兜底初始化（后续客户端头可自动纠偏）；守卫不可用告警聚合在 `/overview` 内返回；告警聚合采用按 frequency tier 自适应的最小事件阈值与 escalation 阈值策略（reason count + ratio）；前台活跃上报 `POST /cognitive-clock/activity`（聊天输入框调用，对所有用户挂载）；认知时钟状态与 T1 触发由 `cognitive_clock_console.py` 提供。 | ✅ |
| `pending.py` | 模块 | 待处理记忆 API 操作层。提供待处理记忆的审批流管理（列表/审批/拒绝/批量）与结构化元数据（置信度/类别/有效期/依据）投影；审批透传审批者改写文本 `edited_content`（不可编辑的提案 → 400；提案所针对的记忆在入队后已变化 → 409 且提案保持待审），遗忘类提案批准即归档目标记忆（保留期内可恢复）；批准/拒绝（含批量）统一经 `pending_review` 写审计。 | ✅ |
| `conflicts.py` | 模块 | 待裁决记忆冲突 API 操作层。列出并裁决 `pending_memories.is_conflict` 记录，复用 Harness 记忆变更（`update_memory` / `add_knowledge`）保持新旧事实生命周期一致；裁决结果经 `pending_review.record_pending_event` 写入操作账本。 | ✅ |
| `shared_context/`（子包） | 模块 | 共享上下文 API 子域：CRUD、健康检查、历史证据、遗留迁移 + 序列化辅助。5 个 `shared_context_*` 模块聚合于此，`shared_context/__init__.py` 为聚合门面统一 re-export | ✅ |
| `reindex.py` | 模块 | 嵌入模型迁移 API：`GET /reindex/estimate` 返回旧模型遗留、待迁移的记忆总数（`total_memories`，前端只用这个数）；`POST /reindex` 202 启动（已有同一嵌入模型的进行中则加入同一轮，另一模型的进行中返回 409；经 `services/memory/reindex_run.py` 后台执行，不占用请求）；`GET /reindex/status` 返回 idle/running/succeeded/failed 与 done/total/结果（migrated/skipped/failed）。 | ✅ |
| `radar.py` | 模块 | 动态偏好雷达 API。暴露当前会话雷达状态、手动微调与隐式反馈记录 HTTP 接口。 | ✅ |
| `tool_guidance.py` | 模块 | 工具规约与动态经验 API。暴露工具黄金指南列表（JIT 合成）、人工置顶/取消置顶与规则清理端点；只有 Memory Labs 的工具指引面板调用，仅在 `MYRM_MEMORY_LABS=1` 时挂载。 | ✅ |
| `working_state.py` | 模块 | Working State API — cross-session task continuity endpoint. 提供读/写/清除 `__working_state` Profile 属性的 HTTP 入口。 | ✅ |
| `domain_mesh.py` | 模块 | 三域认知网格（User/Assistant/Task）渐进式 L0/L1/L2 记忆聚合概览、与单条下钻 API，采用确定性启发式兜底保障存量与外部条目口径一致。 | ✅ |

