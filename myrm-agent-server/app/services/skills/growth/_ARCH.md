# skills/growth/ 模块架构

## 架构概述

技能成长子域。提供成长动作类型 SSOT、case DTO、成长 case 查询、账本审计、账本投影与成长生命周期编排。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `constants.py` | 核心 | `GROWTH_ACTION_TYPES` SSOT；`is_background_growth_approval()` 供 drafts API 与 ApprovalRegistry 分流 | ✅ |
| `case_types.py` | 核心 | 技能成长 case DTO：Summary（列表）与 Detail（单条按需拉取） | ✅ |
| `queries.py` | 核心 | 审批主链 evolution / draft case 查询；列表 summary、detail 单条加载；stats SQL 分桶计数；list merge fetch=limit+offset | ✅ |
| `audit_queries.py` | 核心 | Ledger 事件审计与 timeline 查询（audit entries / stats / timeline） | ✅ |
| `lifecycle.py` | 核心 | 技能成长统一编排入口。接收 Harness 复盘结果，按类型与风险决定自动落地、人工审核、锁定拦截或扫描失败降级（新技能自动落盘前依次过：锁定/已存在 → 语义去重 → CRITICAL 预检 → `scan_risk_policy` 高危新增复核，命中即落人工审核草稿并记录 `risk:` 信号与扫描摘要）；每条人工审核都以结构化原因码（`risk:` / `similar:` / `scan_failed` / `evolution_locked` / `apply_failed`）与 `apply_error` 落库，`description` 始终是纯技能描述；自动落地只发一条成长事件、不另发 `SKILL_EVOLVED` 提示，前端据此给出撤销入口，撤销即归档、可在技能列表恢复；同名技能再次被提议时走人工审核，审批通过会一并恢复已归档的技能；根据 `deployment_capabilities.allows_local_skills` 判定物化权限（local/sandbox 默认允许，禁用时 fail-closed 跳过），semantic_memory 始终保留 | ✅ |

## 设计原则

- **依赖方向**：constants/case_types ← queries/audit_queries ← lifecycle 单向依赖；跨子域引用根模块（`experience_ledger` / `auto_extractor` / `draft_notification` / `evolution_reviews`）时使用 `..` 相对导入。
- **IMPORT CONSTRAINT**：本包不做聚合导出（条件性依赖环见 `__init__.py`），外部一律穿透导入子模块。
