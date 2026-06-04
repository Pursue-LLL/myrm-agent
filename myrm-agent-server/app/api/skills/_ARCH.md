# api/skills 模块架构


---

## 架构概述

技能管理接口。提供本地技能管理、预置技能列表、技能发现市场（5 源搜索+安装+卸载+更新）、技能成长审核与技能打包功能。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `router.py` | ✅ 入口 | 子路由注册（统一暴露 prebuilt, local, packaging, discovery, drafts, config, core, curator 等） |
| `drafts.py` | ✅ 核心 | 技能草稿审查 API（以 `ApprovalRecord` 为事实源，含采纳落盘 + 名称 slug 化 + 智能补丁合并应用 + 审核状态事件广播 + 统一 ledger 写入） |
| `config.py` | ✅ 核心 | 用户技能配置（启用/禁用 + 安全扫描 + 一键回滚 + 信任授权） |
| `core.py` | ✅ 核心 | 技能 CRUD 基础端点（列表与详情） |
| `growth.py` | ✅ 核心 | 统一技能成长查询 API。提供 case 列表、runtime failure 证据与负向审计查询，供设置页技能成长中心与成长审计页复用 |
| `experience_ledger.py` | ✅ 核心 | 经验账本查询 API。提供原始 ledger 事件，以及 skill-growth 投影事件/汇总视图（含 `APPLY_FAILED`） |
| `discovery.py` | ✅ 核心 | 技能发现市场 API（搜索/预览/安装/卸载/URL安装/智能URL解析/更新检查/更新） |
| `evolution/` | ✅ 核心 | 提供 evolution 手动审核 API（以 `ApprovalRecord` 为唯一事实源，含 `approve/reject/rollback` 与 apply-failed retry 语义）；旧 `/rejections` 审计接口已改为转读统一技能成长审计服务 |
| `ws_evolution.py` | ✅ 核心 | WebSocket 接口，负责向前端实时推送新的 EvolutionProposal |
| `sync.py` | ✅ 核心 | 统一数据同步协议（导出/导入本地技能 ZIP 包，包含底层强制静默安全扫描，解决端到端数据孤岛问题） |
| `batch_import.py` | ✅ 核心 | 批量导入协议（针对 Hermes 协议和 ZIP 归档的批量技能解压、冲突检测、安全扫描与落盘） |
| `_staging.py` | ✅ 辅助 | 批量导入的持久化暂存区 (Persistent Staging Area / Claim Check) 管理，实现大文件安全异步流转与原子写 |
| `instances.py` | ✅ 核心 | 多实例 CRUD API 路由（状态管理已下沉至 `core/skills/state_manager_instance.py`） |
| `config_version.py` | ✅ 辅助 | Re-export wrapper（单一来源：`core/skills/config_version.py`） |
| `local.py` | ✅ 核心 | 本地技能管理（上传、安装、卸载） |
| `packaging.py` | ✅ 核心 | 技能打包（导出为 ZIP，集成脱敏引擎，支持两段式 Diff 预览与细粒度脱敏控制） |
| `permissions.py` | ✅ 核心 | 技能权限授权 CRUD + 使用统计 |
| `history.py` | ✅ 核心 | 技能版本历史 + 回滚 |
| `prebuilt.py` | ✅ 核心 | 预置技能列表 + reset-to-default + accept-upstream 更新管理 |
| `curator.py` | ✅ 核心 | Skill Curator API — lifecycle actions (pin/unpin/restore/archive), config CRUD, manual sweep, history, consolidation preview/execute |
| `schemas.py` | ✅ 辅助 | 请求/响应 Pydantic 模型 |
| `templates.py` | ✅ 辅助 | 内置实例模板常量 |

## 关联服务

| 文件 | 职责 |
|------|------|
| `app/services/skills/growth_lifecycle.py` | 统一技能成长生命周期编排 |
| `app/services/skills/draft_notification.py` | 技能成长记录持久化 + 安全预检 + SSE 通知发布 + 技能成长 ledger 镜像 |
| `app/services/skills/evolution_reviews.py` | evolution 审核生命周期服务（ApprovalRecord 唯一事实源 + apply-failed/rollback） |
| `app/database/models/approval.py::ApprovalRecord` | 技能成长/语义记忆审批记录事实源 |
| `app/services/skills/experience_ledger.py` | 技能成长生命周期账本（`review_required/approved/rejected/blocked/failed_scan`） |
| `app/services/skills/growth_queries.py` | 统一技能成长查询服务（当前 case + 负向审计 + 仪表盘时间线） |
| `app/services/skills/growth_projection_queries.py` | skill-growth 账本投影查询服务（经验账本 projection 事件/摘要，含 `APPLY_FAILED` 负向状态） |
| `app/core/skills/curator_service.py` | Skill Curator 业务服务（配置持久化、sweep 执行、background task 编排、consolidation 集成与 agent 引用重写） |

---

## 依赖关系

- `app/services/`：技能业务逻辑
- `app/services/skills/`：成长生命周期 / 草稿通知 / 自动物化服务
- `app/core/skills/creation/service.py`：技能创建落盘服务（采纳时调用）
- `app/core/memory/adapters/setup.py`：记忆管理器工厂（语义记忆采纳时调用）
- `app/api/dependencies.py`：认证依赖注入
- `app/api/events/event_bus.py`：SSE 事件总线
