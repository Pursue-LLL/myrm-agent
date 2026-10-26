# services/wiki 模块架构


## 架构概述

Wiki 知识库服务层：Memory→Wiki 归档、vault 路径 SSOT、启动迁移、compaction 后 SessionNotes 后台归档。REST `/api/wiki/stats` 返回 **cognitive map** 字段与 **`structural_issues`**（deterministic broken markdown/wikilink links — path + frontmatter title alias — invalid frontmatter types，raw-backed provenance gaps，120s TTL 缓存 via `structural_stats_cache.py`）。

## Vault SSOT

- **Canonical path**: `{harness_dir}/wiki/agents/{agent_id}/` — `vault.resolve_wiki_vault_path(agent_id)`
- **Shared read-only**: `{harness_dir}/wiki/shared/{context_id}/` — via `resolve_shared_wiki_vault_path()`
- **Legacy paths** (one-time migration): `{state_dir}/wiki`, `~/.myrm/users/sandbox/wiki`
- **Startup**: `vault.init_wiki_vault_at_startup()` from FastAPI lifespan
- **Shared archiver**: `vault.get_wiki_archiver(llm)` — API、SessionNotes 归档、Deep Research vault、consolidation digest 共用；必须带模型（无模型直接 `TypeError`）
- **Vault 布局（无模型）**: `vault.get_wiki_structure(agent_id)` — 去重扫描、卫生清单、`.wikiignore`、原文落盘等只读写文件的场景，不构造 archiver、不启动编译 worker

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出 | — |
| `memory_to_wiki.py` | 核心 | 记忆转 Wiki（`publish_raw` + enqueue compile；security_blocked 跳过）；支持 harness SessionNotes 与 legacy JSON；`query_wiki` 返回结构化 QueryResult | ✅ |
| `vault/` | 域 | vault 生命周期 + 路径 SSOT + export + git hooks；见 [`vault/_ARCH.md`](vault/_ARCH.md) | ✅ |
| `maintain/` | 域 | maintain 编排 + schemas + state 持久化；见 [`maintain/_ARCH.md`](maintain/_ARCH.md) | ✅ |
| `daily_review/` | 域 | 每日复盘知识化 — 复盘原文 verbatim 存证（`ingest.py` → raw/DailyReview）+ 四维分流提取提示词（`prompts.py` 注入 archiver compiler）+ cron 汇总兜底（`runner.py`，`__wiki_daily_review_compound__`）+ 四张标准模板幂等种子（`templates.py`，marker 防复活用户删除）；见 `daily_review/prompts.py` 等 | ✅ |
| `governance/` | 域 | 知识生命周期治理（老化扫描 90d + 归档 + 撤销 + 复活）；见 [`governance/_ARCH.md`](governance/_ARCH.md) | ✅ |
| `obsidian/` | 域 | Obsidian 导入适配 + export presets；见 [`obsidian/_ARCH.md`](obsidian/_ARCH.md) | ✅ |
| `agent_scope.py` | 辅助 | chat_id → agent_id（vault 选择）+ agent_id → UserConfig scope key 规范化（state/config store 共用） | ✅ |
| `_userconfig_scoped.py` | 辅助 | 共享 UserConfig scoped JSON 持久化（load/save/merge，agent-scoped） | ✅ |
| `wiki_archive_hook.py` | 钩子 | compaction persist 后 SessionNotes 后台归档（按 chat.agent_id 选 vault） | ✅ |
| `consolidation_bridge.py` | 钩子 | consolidation 完成后 insight → `publish_raw` + enqueue（上游 enable_wiki 门控） | ✅ |
| `structural_stats_cache.py` | 辅助 | `/wiki/stats` structural lint 120s TTL 缓存；`_after_wiki_vault_mutation` SSOT 在 maintain/repair-types/repair-publication/move/import/apply/delete concept/delete folder/pending approve/delete raw 等变更后失效；后台 worker 编译写入的变更由 ingest 快照的 vault 指纹变化触发失效 | ✅ |
| `knowledge_query_service.py` | SSOT | `execute_wiki_knowledge_query` — Settings POST /query 与 Chat Wiki Knowledge Lane 共用零 LLM 检索 + citations，支持通过 shared_context_ids 挂载多库跨源检索与友好标签解析；证据不足时反射引擎 `refused` 判定并返回拒答文案（清空 sources，与 REST `refused` 字段一致） | ✅ |
| `vault/service.py` | SSOT | `get_wiki_archiver` 进程级缓存单例（严格按 llm, agent_id, manager, public_dirs, public_dir_labels 联合维度多重隔离，彻底根除跨库与会话挂载污染；无模型 `TypeError`）· `get_wiki_structure` 不带 archiver 的 vault 布局 | ✅ |
| `chat_compound_service.py` | SSOT | `stage_chat_compound_from_message` — POST /compound DB hydrate Q&A + trust → harness pending；reject inactive/incognito assistant messages | ✅ |
| `health_report_service.py` | SSOT | GET /wiki/health-report structural scan + merge vault full snapshot drift + `count_open_actions`；maintain 写入/读取 `reports/last-health.json`；健康报告响应模型 `WikiHealthIssueResponse` / `WikiHealthReportResponse` 的唯一定义（路由直接导入） | ✅ |
| `dedup_runner.py` | SSOT | `schedule_wiki_dedup_scan` (202 background) / `run_wiki_dedup_scan_job` (cron blocking) / `run_post_sync_dedup_scan`（来源同步后的尽力增量扫描，仅在扫描真正完成时返回 True）/ `apply_wiki_dedup_disposition` / `wiki_dedup_checklist_ready` — POST /dedup/* 与 Cron `__wiki_dedup__` 共用；REST/Cron 扫描在 compile 进行中 skip，来源同步后的扫描不 skip（它审的文件本就被暂扣在该 compile 之外）；扫描只读 raw 写去重库，不构造 archiver；同一 vault 的扫描一次只跑一个，「扫描进行中」状态也按 vault 记（`None` 与 `"default"` 是同一个 vault），较旧的扫描不会覆盖较新的分组 | ✅ |
| `clip/` | 核心 | Browser extension clip — `form.py` 8MB cap · `runner.py` async jobs → harness `publish_clip_ingress` · post-write ingest SSE；见 [`clip/_ARCH.md`](clip/_ARCH.md) | ✅ |
| `knowledge_pack/` | 域 | 知识包前置主动注入（`KnowledgePackProactiveInjectionPerAgentTurn`）— schemas DTO · selector Jaccard 相似度去重与硬预算截断；见 [`knowledge_pack/_ARCH.md`](knowledge_pack/_ARCH.md) | ✅ |
| `wiki_query_intent.py` | 辅助 | Chat Wiki Knowledge Lane 确定性准入闸门（`should_use_wiki_knowledge_lane`） | ✅ |
| `asset_index_service.py` | 核心 | Obsidian wiki/assets vision caption 索引；`build_vision_fallback_engine_from_providers` 有序视觉链；import 与手动 compile 后 `schedule_wiki_asset_index` 后台运行并在完成后 publish ingest snapshot；maintain 同步 `run_wiki_asset_index` | ✅ |
| `ingest_events.py` | 核心 | Wiki ingest SSE event bus；scope refcount 单 poll；best-effort publish；queue/compile snapshot；snapshot stats 含 **`synthesis_pending_count`**；**tree_sync_required** / **stats_refresh_required** 信号 → FE REST 刷新；指纹并入本地可写 `concepts/` 编译页 stat（mtime_ns+size），Agent 编辑词条 → UI 自动刷新 | ✅ |
| `source_sync/` | 核心 | Gmail/GDrive/RSS/Zotero 确定性 pull → `publish_raw` → post-sync dedup scan → compile enqueue（经 `deferred_enqueue` 在扫描后放行，待审重复文档不被编译两次）；Integration mirror；Cron router；腾讯 ima 知识库/笔记导入（`ima/` 子包：可续跑清单 + 逐条账本 + 分片同步 cron `__wiki_ima_sync__`，首次回填的编译须用户确认）；闭包：HTML2Markdown、Cron hygiene、sync state、Second Brain Gmail 默认 | ✅ |
| `writeback/` | 域 | 任务使用台账与作者审阅单驱动的选择性回写引擎；见 [`writeback/_ARCH.md`](writeback/_ARCH.md) | ✅ |
