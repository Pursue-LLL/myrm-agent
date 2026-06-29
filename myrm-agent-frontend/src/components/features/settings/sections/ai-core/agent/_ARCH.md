# ai-core/agent/ 模块架构

## 架构概述

`AgentEditPanel` 各配置 Tab 的子组件。per-agent 设置 UI，不含路由逻辑。

## 文件清单

| 文件 | 职责 |
|------|------|
| `AgentBasicInfoTab.tsx` | 名称、描述、头像等基础信息 |
| `AgentCapabilitiesTab.tsx` | 模型绑定、引擎参数、共识、会话策略等能力 Tab 入口 |
| `AgentCapabilitiesTabSections.tsx` | 能力 Tab 基础区段（模型/迭代/工作区/引擎参数） |
| `AgentCapabilitiesConsensusSection.tsx` | 多模型共识配置区段 |
| `AgentCapabilitiesSessionSection.tsx` | 会话策略区段 |
| `AgentInstinctInboxTab.tsx` | **Agent Draft Inbox（洞察 tab）**：审阅后台 growth `skill_draft`，走 `/skills/drafts` API |
| `AgentSecretsTab.tsx` | Agent 级密钥 |
| `AgentSecurityTab.tsx` | 安全策略 |
| `AgentSubagentBinding.tsx` | 子智能体绑定 |
| `AgentSharedContextBinding.tsx` | 共享上下文绑定 |
| `AgentOpenAPIServicesTab.tsx` | OpenAPI 服务 |
| `AgentProfileTimeMachine.tsx` | 配置时光机 |
| `AgentBrowserConfigSection.tsx` | 浏览器配置卡片（引擎、来源、弹窗策略、录制） |
| `AgentNotifyTargets.tsx` | 通知目标 |
| `AgentPreviewCard.tsx` | 预览卡片 |

## 与全局审批的区别

| UI | 数据源 | 场景 |
|----|--------|------|
| 本目录 `AgentInstinctInboxTab` | `/api/v1/skills/drafts` | 后台 Observer 产出的 per-agent 洞察 |
| 全局 `ApprovalDrawer` | `/api/v1/approvals` | 对话内 inline HITL（含 `thread_id` 的 skill_draft） |
| 设置→技能→待审 | `reviews` / growth 中心 | 全站 skill growth 队列 |

## 依赖

- [sections/_ARCH.md](../../_ARCH.md)
- `@/services/skill` — drafts list/approve/reject
