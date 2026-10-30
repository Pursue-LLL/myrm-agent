# api/skills/evolution/

## 架构概述

技能进化 HTTP 层：触发 derive/fix、pending 审核、历史回滚。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Evolution API - Pending Evolutions & LLM Confirmation Rejection Logs | ✅ |
| `derive.py` | 模块 | Evolution API endpoint for triggering derived evolution; the skill is resolved to its evolution row and refused when locked (404 / 409) before the instruction is screened by the risk gate (400 `risk_held`) and reaches the evolution engine | ✅ |
| `fix.py` | 模块 | Evolution API endpoint for triggering FIX evolution with GUI-First force retry support; a locked skill is refused (409) even when the retry is forced | ✅ |
| `helpers.py` | 模块 | Evolution API 共享 helper：`_evolution_lineage_id`、`_get_skill_store`、`_get_skill_store_db_path`（委托 core evolution_store）；`_require_evolvable_record` 把页面 id / 行 id / 技能名解析成进化库的行（没有行的本地页面技能经 `evolution_record_for_page_skill` 补建一行，通过锁检查后才保存，SKILL.md 超出存储上限为 422；未知技能、非本地技能、SKILL.md 缺失为 404），并按引擎同一标准（`skill_from_disk`：库标志或 SKILL.md 里的锁）拒绝被锁的技能（409，强制重试同样不绕过；引擎在应答之后才丢弃被锁的请求，所以必须在入口预检） | ✅ |
| `history.py` | 模块 | evolution 历史记录接口层。对外提供已处理的 evolution 历史查询（GET /history）与单条回滚（POST /{id}/rollback）。 | ✅ |
| `pending.py` | 模块 | evolution 审核接口层。对外提供 pending 列表、approve、reject、revise，以 ApprovalRecord 为唯一事实源；列表与详情均携带 `impacted_dependents`（经 core/skills/dependency_guard 查询）；approve 响应带 `apply_status`、`apply_error`、`remediation` 与稳定的 `reason_code`（`apply_failed` / `stale_base` / `skill_md_unloadable`），前端据此给出本地化说明，不展示 `apply_error` 原文；reject 对已批准但应用失败的提案同样有效，对已落地的返回 409。 | ✅ |
