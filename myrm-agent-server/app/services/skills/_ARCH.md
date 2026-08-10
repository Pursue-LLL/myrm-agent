# services/skills 模块架构

## 架构概述

技能成长相关服务层。提供技能权限管理、经验账本、统一成长生命周期编排，以及草稿/成长事件持久化服务。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `permission_service.py` | 核心 | 技能权限管理服务 | — |
| `experience_ledger.py` | 核心 | 学习资产事件账本（append-only，统一记录 migration/evolution/review/skill_growth 事件，并提供技能成长聚合查询） | ✅ |
| `growth/` | 核心 | 技能成长子模块：case DTO、审批主链查询、账本投影/审计查询、统一生命周期编排与常量 SSOT（见 `growth/_ARCH.md`） | ✅ |
| `evolution_review/` | 核心 | evolution 审核子模块：域类型、ApprovalRecord 持久化、查询/动作、落盘编排与内容 apply+rollback（见 `evolution_review/_ARCH.md`） | ✅ |
| `evolution_growth.py` | 核心 | Harness 演化提案到 Server 技能成长生命周期的适配层（含 form routing: skill_draft/cron_suggestion/skip），以 ApprovalRecord 为唯一事实源 | ✅ |
| `auto_extractor.py` | 核心 | 技能物化辅助器。仅负责把已通过策略判断的成长结果落盘成真实技能或补丁，并发布 `SKILL_EVOLVED` 事件 | ✅ |
| `draft_notification.py` | 核心 | 技能成长记录持久化 + 安全预检 + 24h 去重 + `ApprovalRecord` rich status 落库 + `SKILL_GROWTH_UPDATED` / `NEW_SKILL_DRAFT` 事件发布 + ledger 镜像 | ✅ |
| `evolution_reviews.py` | 核心 | evolution 审核生命周期门面（re-export）；实现见 `evolution_review/` | ✅ |
| `similarity_checker.py` | 核心 | 技能语义去重实现。基于 HybridSkillSearchEngine 检查新技能是否与已有技能功能重复，防止技能熵增 | ✅ |
| `quality_alert_webhook.py` | 辅助 | 技能质量主动监控与告警 webhook | — |
| `ws_hub.py` | 核心 | Evolution WebSocket 连接池与广播（`broadcast_proposal` / `broadcast_message`） | ✅ |
| `evolution_events.py` | 辅助 | 技能进化 `SKILL_EVOLVED` 事件发布（services 层单一入口） | ✅ |
