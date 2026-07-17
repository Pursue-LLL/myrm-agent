# services/skills 模块架构

## 架构概述

技能成长相关服务层。提供技能权限管理、经验账本、统一成长生命周期编排，以及草稿/成长事件持久化服务。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `permission_service.py` | 核心 | 技能权限管理服务 | — |
| `experience_ledger.py` | 核心 | 学习资产事件账本（append-only，统一记录 migration/evolution/review/skill_growth 事件，并提供技能成长聚合查询） | ✅ |
| `growth_case_types.py` | 核心 | 技能成长 case DTO：Summary（列表）与 Detail（单条按需拉取） | ✅ |
| `growth_queries.py` | 核心 | 审批主链 evolution / draft case 查询；列表 summary、detail 单条加载；stats SQL 分桶计数；list merge fetch=limit+offset | ✅ |
| `growth_audit_queries.py` | 核心 | Ledger 事件审计与 timeline 查询（audit entries / stats / timeline） | ✅ |
| `growth_projection_queries.py` | 核心 | 技能成长账本投影查询层。负责把 `skill_growth.*` ledger 事件规范化为 projection 事件列表与摘要，补齐 `APPLY_FAILED` 等负向状态，供经验账本投影接口复用 | ✅ |
| `growth_lifecycle.py` | 核心 | 技能成长统一编排入口。接收 Harness 复盘结果，按类型与风险决定自动落地、人工审核、锁定拦截或扫描失败降级 | ✅ |
| `evolution_growth.py` | 核心 | Harness 演化提案到 Server 技能成长生命周期的适配层（含 form routing: skill_draft/cron_suggestion/skip），以 ApprovalRecord 为唯一事实源 | ✅ |
| `auto_extractor.py` | 核心 | 技能物化辅助器。仅负责把已通过策略判断的成长结果落盘成真实技能或补丁，并发布 `SKILL_EVOLVED` 事件 | ✅ |
| `growth_constants.py` | 核心 | `GROWTH_ACTION_TYPES` SSOT；`is_background_growth_approval()` 供 drafts API 与 ApprovalRegistry 分流 | ✅ |
| `draft_notification.py` | 核心 | 技能成长记录持久化 + 安全预检 + 24h 去重 + `ApprovalRecord` rich status 落库 + `SKILL_GROWTH_UPDATED` / `NEW_SKILL_DRAFT` 事件发布 + ledger 镜像 | ✅ |
| `evolution_reviews.py` | 核心 | evolution 审核生命周期门面（re-export）；实现见 `evolution_review_{types,persistence,queries,actions,disk,disk_content}.py` | ✅ |
| `evolution_review_types.py` | 核心 | evolution 审核域类型与 ApprovalRecord 转换 | ✅ |
| `evolution_review_persistence.py` | 核心 | evolution ApprovalRecord 持久化读写（list/count 下推 SQL LIMIT + pending growth_status 过滤） | ✅ |
| `evolution_review_queries.py` | 核心 | 创建与只读查询（list/count 委托 persistence SQL） | ✅ |
| `evolution_review_actions.py` | 核心 | 审批 / 拒绝 / 修订 / 回滚 | ✅ |
| `evolution_review_disk.py` | 核心 | 落盘编排（description / shadow / approval 成功路径） | ✅ |
| `evolution_review_disk_content.py` | 核心 | 全量内容 apply + rollback（含 fork） | ✅ |
| `similarity_checker.py` | 核心 | 技能语义去重实现。基于 HybridSkillSearchEngine 检查新技能是否与已有技能功能重复，防止技能熵增 | ✅ |
| `quality_alert_webhook.py` | 辅助 | 技能质量主动监控与告警 webhook | — |
| `ws_hub.py` | 核心 | Evolution WebSocket 连接池与广播（`broadcast_proposal` / `broadcast_message`） | ✅ |
| `evolution_events.py` | 辅助 | 技能进化 `SKILL_EVOLVED` 事件发布（services 层单一入口） | ✅ |
