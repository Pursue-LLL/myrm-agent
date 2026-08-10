# services/skills/growth 模块架构

## 架构概述

技能成长（skill growth）子模块。统一编排技能成长生命周期、审批主链查询、账本投影与审计查询、case DTO 与常量 SSOT。与 `../evolution_review/`（evolution 审核域）通过 `ApprovalRecord` 与 `EvolutionReviewRecord` 协作。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `queries.py` | 核心 | 审批主链 evolution / draft case 查询；列表 summary、detail 单条加载；stats SQL 分桶计数 | ✅ |
| `case_types.py` | 核心 | 技能成长 case DTO：Summary（列表）与 Detail（单条按需拉取） | ✅ |
| `audit_queries.py` | 核心 | Ledger 事件审计与 timeline 查询（audit entries / stats / timeline） | ✅ |
| `projection_queries.py` | 核心 | 技能成长账本投影查询层。把 `skill_growth.*` ledger 事件规范化为 projection 事件列表与摘要，补齐负向状态 | ✅ |
| `lifecycle.py` | 核心 | 技能成长统一编排入口。接收 Harness 复盘结果，按类型与风险决定自动落地、人工审核、锁定拦截或扫描失败降级 | ✅ |
| `constants.py` | 核心 | `GROWTH_ACTION_TYPES` SSOT；`is_background_growth_approval()` 供 drafts API 与 ApprovalRegistry 分流 | ✅ |
