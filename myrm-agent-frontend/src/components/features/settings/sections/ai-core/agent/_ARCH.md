# ai-core/agent/ 模块架构

## 架构概述

`AgentEditPanel` 各配置 Tab 的子组件。per-agent 设置 UI，含 per-agent Smart Routing 覆盖配置。

## 文件清单

| 文件                                     | 职责                                                                                                                                                                                                                                                            |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AgentBasicInfoTab.tsx`                  | 名称、描述、头像、**正式韩语回复 Switch**（`engine_params.response_locale_policy`）等基础信息                                                                                                                          |
| `AgentCapabilitiesTab.tsx`               | 模型绑定、引擎参数、共识、会话策略等能力 Tab 入口；顶部 `AgentLoadoutSummary`（`refreshKey`（bind/unbind 与保存后重拉）+ SC tile→`#shared-context-binding`）；`#loadout` 深链；各区段共用的 props 类型 `CapabilitiesSectionProps` 也在此导出                                                                                   |
| `AgentCapabilitiesTabSections.tsx`       | 能力 Tab 基础区段（模型绑定含 org MAP 约束 badge（hook refetch 同步）、ModelSwapContinuityCard 资产连续性保障与模型能力适配、迭代/工作区/**IdleCompactSection** 等）                                                                                   |
| `ModelSwapContinuityCard.tsx`            | 资产连续性保障与底层模型适配卡片（已绑定 Skills/MCP/Memory/Rules 100% 连续保留凭证、所有模型共用的 Execution Discipline 摘要、Vision 兼容与上下文窗口感知）                                                                                                       |
| `AgentCapabilitiesConsensusSection.tsx`  | MoA overlay 参考模型选择器（`ConsensusRefModels`，供 MoaOverlaySection 复用）                                                                                                                                                                                   |
| `AgentCapabilitiesMoaOverlaySection.tsx` | Agent 环 MoA 顾问叠加配置（fanout 包含 user_turn/per_iteration/every_n/risk_triggered 自适应风险触发 / privacy / 参考模型）                                                                                                                                     |
| `AgentCapabilitiesRoutingSection.tsx`    | 路由覆盖区段（跟随全局 / 自定义 / 关闭，自定义时分别指定轻量与推理模型）                                                                                                                                                                                         |
| `AgentCapabilitiesSessionSection.tsx`    | 会话策略区段                                                                                                                                                                                                                                                    |
| `AgentInstinctInboxTab.tsx`              | **Agent Draft Inbox（洞察 tab）**：审阅后台 growth `skill_draft`，走 `/skills/drafts` API                                                                                                                                                                       |
| `AgentSecretsTab.tsx`                    | Agent 级密钥；`listAgentSecrets` 经 service normalize 为 key 名列表；失败 toast 展示后端 detail；保存/删除成功后 invalidate readiness 缓存并 SWR mutate 即时刷新                                                                                                |
| `AgentSecurityTab.tsx`                   | 安全策略（默认会话安全预设三档下拉 + 能力/路径/域名白名单与 blocklist/HITL 超时）+ 审计触发与修复导航；四个字符串列表由 `SecurityChipListEditor` 配置化渲染，状态与校验在 `useSecurityListEditors`                                                                       |
| `SecurityChipListEditor.tsx`             | 安全策略字符串列表卡片（primary / success / danger 三种芯片色调；danger 文字用 `text-destructive-text`；可选 `scrollTargetId` 作为审计修复的滚动高亮目标、可附加子内容）                                                                                       |
| `useSecurityListEditors.ts`              | 允许路径 / 域名白名单 / 域名黑名单 / 命令拒绝列表的输入状态与增删动作；黑名单校验域名格式与重复，命令列表校验重复，输入变化或删除时清除上次错误                                                                                                                |
| `agentSecurityOverrides.ts`              | 安全覆盖配置的数据模型：`KNOWN_CAPABILITIES`、`parseOverrides` / `serializeOverrides`（空配置序列化为 null，路径白名单嵌套在 `pathPolicy`）、`normalizeDomainInput`                                                                                          |
| `HealthScoreCard.tsx`                    | 安全健康评分卡（6 维度分组审计 findings 展示 + policy_gap 分级修复引导）                                                                                                                                                                                        |
| `AgentSubagentBinding.tsx`               | 子智能体绑定：已保存 Agent + 5 个内置专家（Office 3 / browser / explore）；YAML ID 与 UUID 统一显示/移除；浏览器专家缺 Browser 内置工具时阻止添加并打开内置工具面板；无法解析的旧 ID 显示为不可用以便清理。                                                                                                                                 |
| `AgentSharedContextBinding.tsx`          | 共享上下文绑定；`id=shared-context-binding` 锚点；bind/unbind 后 `onBindingsChanged` 通知 loadout 刷新                                                                                                                                                          |
| `AgentOpenAPIServicesTab.tsx`            | OpenAPI 服务；预设选择器的加载/空态/启用文案取自 `agent.openapi.preset*`，`__tests__/AgentOpenAPIServicesTab.test.tsx` 覆盖                                                                                                                                                                                                                                                    |
| `OpenAPIServiceEditor.tsx` / `OpenAPIAuthEditor.tsx` / `openApiTokenBudget.ts`| OpenAPI 服务编辑：单个服务卡片（规格解析、端点勾选、启停、删除）、鉴权类型与凭据字段、直连 token 预算估算                                                                                                                                                                                                                                                                                             |
| `AgentProfileTimeMachine.tsx`            | 配置时光机；加载/回滚失败 toast 展示后端错误 detail                                                                                                                                                                                                             |
| `AgentBrowserConfigSection.tsx`          | 浏览器配置卡片（来源、弹窗策略、录制；引擎由 harness Stealth Ladder 自动路由）                                                                                                                                                                                  |
| `AgentNotifyTargets.tsx`                 | 通知目标（`notify_targets` → server Turn1 加载 `channel_notify_tool`；running 渠道从 `listChannelStatuses` 动态下拉 + pairing/manual ID）                                                                                                                       |
| `AgentTrustedDesktopApps.tsx`            | 预信任桌面应用（`trusted_desktop_apps` → 无人值守运行门禁键域豁免；信任列表联想＋手动输入）                                                                                                                                                                     |
| `AgentFaqTab.tsx`                        | 智能体私有 FAQ 问答库与检索语料配置面板；「重建索引」按钮（有条目时可用）是 FAQ 向量索引的唯一更新入口，条目增删改与导入不动索引，更换嵌入模型后需手动重建 |
| `AgentCapabilitiesDeliverySection.tsx`   | 交付保障策略区段（Delivery Assurance 开关与兜底配置）                                                                                                                                                                                                           |
| `AgentPreviewCard.tsx`                   | 预览卡片                                                                                                                                                                                                                                                        |

## 与全局审批的区别

| UI                             | 数据源                  | 场景                                                |
| ------------------------------ | ----------------------- | --------------------------------------------------- |
| 本目录 `AgentInstinctInboxTab` | `/api/v1/skills/drafts` | 后台 Observer 产出的 per-agent 洞察                 |
| 全局 `ApprovalDrawer`          | `/api/v1/approvals`     | 对话内 inline HITL（含 `thread_id` 的 skill_draft） |
| 设置→技能→待审                 | `reviews` / growth 中心 | 全站 skill growth 队列                              |

## 依赖

- `@/components/features/loadout/AgentLoadoutSummary` — per-agent loadout 摘要
- [sections/_ARCH.md](../../_ARCH.md)
- `@/services/skill` — drafts list/approve/reject
