# services/skills 模块架构

## 架构概述

技能成长相关服务层。按业务域收敛为两个子包：`evolution_review/`（审核域）与 `growth/`（成长域）；根目录保留独立门面文件（账本、草稿通知、权限、语义去重、事件、WebSocket 等）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `evolution_review/` | 子域 | Evolution 审核：类型 + 持久化 + 查询 + 写操作 + 落盘编排（清单见 [`evolution_review/_ARCH.md`](evolution_review/_ARCH.md)） | — |
| `growth/` | 子域 | 技能成长：动作 SSOT + case DTO + case 查询 + 账本审计/投影 + 生命周期编排（清单见 [`growth/_ARCH.md`](growth/_ARCH.md)） | — |
| `evolution_reviews.py` | 门面 | evolution 审核生命周期门面（re-export `evolution_review/` 公共 API） | ✅ |
| `experience_ledger.py` | 核心 | 学习资产事件账本（append-only，统一记录 migration/evolution/review/skill_growth 事件，并提供技能成长聚合查询） | ✅ |
| `draft_notification.py` | 核心 | 技能成长记录持久化 + 安全预检 + 24h 去重 + `ApprovalRecord` rich status 落库 + `SKILL_GROWTH_UPDATED` 事件发布单一出口 + `NEW_SKILL_DRAFT` 事件发布 + ledger 镜像 | ✅ |
| `auto_extractor.py` | 核心 | 技能物化辅助器。仅负责把已通过策略判断的成长结果落盘成真实技能或补丁，并发布 `SKILL_EVOLVED` 事件 | ✅ |
| `permission_service.py` | 核心 | 技能权限管理服务：per-session 缓存、授权加载、卸载时清除授权/审计数据 | ✅ |
| `similarity_checker.py` | 核心 | 技能语义去重实现。基于 HybridSkillSearchEngine 检查新技能是否与已有技能功能重复，防止技能熵增 | ✅ |
| `evolution_events.py` | 辅助 | 技能进化 `SKILL_EVOLVED` 事件发布（services 层单一入口） | ✅ |
| `ws_hub.py` | 核心 | Evolution WebSocket 连接池与广播（`broadcast_proposal` / `broadcast_message`） | ✅ |

## 设计原则

- **按域收敛**：多文件业务域必须收进以域命名的子目录（`evolution_review/`、`growth/`），根目录只保留单文件门面与独立域模块；子包内部跨模块引用用相对导入，跨子域引用用 `..` 相对导入。
- **禁止聚合导出**：子包 `__init__.py` 不做聚合（`experience_ledger → growth.* → evolution_reviews → evolution_review.types → experience_ledger` 条件性依赖环——仅当两包同时聚合导出时才构成循环导入），外部一律穿透导入子模块；公共 API 由 `evolution_reviews.py` 门面统一 re-export。
