# ai-core/agent/ 模块架构

## 架构概述

`AgentEditPanel` 各配置 Tab 的子组件。per-agent 设置 UI，含 per-agent Smart Routing 覆盖配置。

## 文件清单

| 文件 | 职责 |
|------|------|
| `AgentBasicInfoTab.tsx` | 名称、描述、头像、**正式韩语回复 Switch**（`engine_params.response_locale_policy`）等基础信息 |
| `AgentCapabilitiesTab.tsx` | 模型绑定、引擎参数、共识、会话策略等能力 Tab 入口；顶部 `AgentLoadoutSummary`（`refreshKey` + SC tile→`#shared-context-binding`）；`#loadout` 深链 |
| `AgentCapabilitiesTabSections.tsx` | 能力 Tab 基础区段（模型绑定含 org MAP 约束 badge（hook refetch 同步）、路由覆盖/迭代/工作区/**IdleCompactSection** 等） |
| `AgentCapabilitiesConsensusSection.tsx` | MoA overlay 参考模型选择器（`ConsensusRefModels`，供 MoaOverlaySection 复用） |
| `AgentCapabilitiesMoaOverlaySection.tsx` | Agent 环 MoA 顾问叠加配置（fanout / privacy / 参考模型） |
| `AgentCapabilitiesSessionSection.tsx` | 会话策略区段 |
| `AgentInstinctInboxTab.tsx` | **Agent Draft Inbox（洞察 tab）**：审阅后台 growth `skill_draft`，走 `/skills/drafts` API |
| `AgentSecretsTab.tsx` | Agent 级密钥；`listAgentSecrets` 经 service normalize 为 key 名列表；失败 toast 展示后端 detail |
| `AgentSecurityTab.tsx` | 安全策略（能力/路径/域名白名单与 blocklist/HITL 超时）+ 审计触发与修复导航 |
| `HealthScoreCard.tsx` | 安全健康评分卡（6 维度分组审计 findings 展示 + policy_gap 分级修复引导） |
| `AgentSubagentBinding.tsx` | 子智能体绑定 |
| `AgentSharedContextBinding.tsx` | 共享上下文绑定；`id=shared-context-binding` 锚点；bind/unbind 后 `onBindingsChanged` 通知 loadout 刷新 |
| `AgentOpenAPIServicesTab.tsx` | OpenAPI 服务 |
| `AgentProfileTimeMachine.tsx` | 配置时光机；加载/回滚失败 toast 展示后端错误 detail |
| `AgentBrowserConfigSection.tsx` | 浏览器配置卡片（来源、弹窗策略、录制；引擎由 harness Stealth Ladder 自动路由） |
| `AgentNotifyTargets.tsx` | 通知目标（`notify_targets` → server Turn1 加载 `channel_notify_tool`；running 渠道从 `listChannelStatuses` 动态下拉 + pairing/manual ID） |
| `AgentPreviewCard.tsx` | 预览卡片 |

## 与全局审批的区别

| UI | 数据源 | 场景 |
|----|--------|------|
| 本目录 `AgentInstinctInboxTab` | `/api/v1/skills/drafts` | 后台 Observer 产出的 per-agent 洞察 |
| 全局 `ApprovalDrawer` | `/api/v1/approvals` | 对话内 inline HITL（含 `thread_id` 的 skill_draft） |
| 设置→技能→待审 | `reviews` / growth 中心 | 全站 skill growth 队列 |

## 依赖

- `@/components/features/loadout/AgentLoadoutSummary` — per-agent loadout 摘要
- [sections/_ARCH.md](../../_ARCH.md)
- `@/services/skill` — drafts list/approve/reject
