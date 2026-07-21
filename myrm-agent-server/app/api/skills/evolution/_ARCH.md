# api/skills/evolution/

## 架构概述

技能进化 HTTP 层：触发 derive/fix、pending 审核、历史回滚。上级文档：[../../_ARCH.md](../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Evolution API - Pending Evolutions & LLM Confirmation Rejection Logs | ✅ |
| `derive.py` | 模块 | Evolution API endpoint for triggering derived evolution | ✅ |
| `fix.py` | 模块 | Evolution API endpoint for triggering FIX evolution with GUI-First force retry support | ✅ |
| `helpers.py` | 模块 | Evolution API 共享 helper：`_evolution_lineage_id`、`_get_skill_store`、`_get_skill_store_db_path`（委托 core evolution_store） | ✅ |
| `history.py` | 模块 | evolution 历史记录接口层。对外提供已处理的 evolution 历史查询（GET /history）与单条回滚（POST /{id}/rollback）。 | ✅ |
| `pending.py` | 模块 | evolution 审核接口层。对外提供 pending 列表、approve、reject、revise，以 ApprovalRecord 为唯一事实源。 | ✅ |
| `rejections.py` | 模块 | Return unified skill-growth negative audit records via the legacy evolution endpoint. | ✅ |
