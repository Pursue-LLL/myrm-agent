# components/agent/

## 架构概述

跨 feature 共用的智能体 UI 原语（头像、图标、选择器、编辑表单、内置智能体 i18n）。业务页面在 `features/`（如 `chat-window/agent-config-panel`、`settings/.../AgentsSection`），本目录只放可复用展示与编辑组件。

## 文件清单

| 文件                                          | 地位 | 职责                                                                                                                                                                                                                                             | I/O/P |
| --------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `AgentAvatar.tsx`                             | 核心 | 智能体头像（icon/lucide/emoji/image/首字母）                                                                                                                                                                                                     | ✅    |
| `agent-icons.tsx`                             | 核心 | 内置智能体 SVG 图标注册表与 `AgentIcon`                                                                                                                                                                                                          | ✅    |
| `lucide-icon-resolver.tsx`                    | 核心 | 按名称（kebab/PascalCase）解析 Lucide 图标：`findLucideIcon`（未知返回 null）/`resolveLucideIcon`（回退 Bot），每个图标经 `DynamicIcon` 异步加载自己的 chunk；禁止 `import * as` 整库引入                                                        |
| `builtin-agent-i18n-data.ts`                  | 核心 | 内置智能体 i18n 数据 SSOT（key 须与 server `_BUILTIN_AGENTS` id 一一对应；`__tests__/builtin-agent-i18n-data.test.ts` + server `test_builtin_agent_i18n_parity.py` 守护）                                                                        | ✅    |
| `builtin-agent-i18n.ts`                       | 核心 | 内置智能体 locale 解析（getBuiltinAgentName/Description）                                                                                                                                                                                        | ✅    |
| `AgentEditForm.tsx`                           | 辅助 | 智能体创建/编辑表单壳（react-hook-form + zod 管名称/描述/指令，其余字段收敛为一个 `AgentExtraFields` 状态由各区段共用 `value/onChange`；打开新建时全部字段回到默认值）                                                                          | ✅    |
| `agentEditFormModel.ts`                       | 核心 | 表单纯逻辑：zod 校验、`AgentExtraFields` 模型、详情回填 `formValuesFromAgent` / `extraFieldsFromAgent` 与提交载荷 `buildAgentPayload`（默认策略提交 null、命令绑定过滤、验收清单裁剪至 20 行）                                                      | ✅    |
| `AgentEditAvatarField.tsx`                    | 辅助 | 头像区段：点击头像选文件（上传逻辑见 `useAgentAvatarUpload`）+ 内置图标网格                                                                                                                                                                      | ✅    |
| `useAgentAvatarUpload.ts`                     | 辅助 | 头像文件选择与上传：先本地预览，已保存的智能体再上传并回填服务端 URL，失败 toast；新建时仅保留预览                                                                                                                                              | ✅    |
| `AgentEditResponsibilityFields.tsx`           | 辅助 | 责任区段：责任范围、负责人、验收清单                                                                                                                                                                                                              | ✅    |
| `AgentEditBrowserSettings.tsx`                | 辅助 | 浏览器区段：浏览器来源（含扩展/云浏览器风险提示）、弹窗处理、会话录制                                                                                                                                                                            | ✅    |
| `AgentEditSessionPolicy.tsx`                  | 辅助 | 会话策略区段：开关 + 模式（持久/每日/空闲）+ 重置小时或空闲分钟（1–10080）                                                                                                                                                                       | ✅    |
| `DescribedSelectItem.tsx`                     | 辅助 | 带说明行的下拉选项，表单内各策略下拉共用                                                                                                                                                                                                          | ✅    |
| `CommandBindingsEditor.tsx`                   | 辅助 | Agent 斜杠命令绑定列表编辑                                                                                                                                                                                                                       | ✅    |
| `GovernancePanel.tsx`                         | 辅助 | 责任单元治理面板（孤儿/重叠展示 + 孤儿直删；仅 needs_attention 时渲染）；区域标签取自 `Agent.governance.regionLabel`，`__tests__/GovernancePanel.test.tsx` 覆盖                                                                                  | ✅    |
| `GovernanceMergeWizard.tsx`                   | 辅助 | 合并向导（来源/目标双选 + dry-run 明细 + typed确认 + 成功后Undo；成功后锁定选项防错位）                                                                                                                                                          | ✅    |
| `AgentSetupWizard.tsx`                        | 辅助 | 新手向导（模板选择 → 设置预览门控 → 就绪检查 → 试用对话 → 完成；集成 `AgentSettingsPreviewGate` 消除盲盒创建；toC 文案经 `Agent.setupWizard` i18n）                                                                                              | ✅    |
| `AgentSettingsPreviewGate.tsx`                | 核心 | 智能体创建前全量设置预览门控面板（5 维核心配置矩阵：Built-in Tools, Skills Pack, MCP Connectors, Memory Engine, Deploy Mode & Sandbox Bounds；Pre-flight 状态徽标与确认创建门控）                                                                | ✅    |
| `DualLayerMemoryCard.tsx`                     | 核心 | 用户画像与智能体工作笔记双层结构化看板（USER / MEMORY 两层容量水位指示器与垃圾记忆准入探针）；全部文案取自 `memory.dualLayer` 六语言命名空间                                                                                                     | ✅    |
| `WatermarkBar.tsx`                            | 辅助 | 单层记忆容量水位条（已用 / 上限字符、等级徽标、服务端告警）与 `levelForRatio`（编辑中按 70% / 90% / 100% 阈值本地推导等级，与服务端一致）；文案取自 `memory.dualLayer`                                                                           | ✅    |
| `AgentReadinessList.tsx`                      | 辅助 | 就绪度逐项列表（文案来自 `useReadinessText`），`withLinks` 时为未就绪项提供设置深链；新手向导与插件导入结果页共用                                                                                                                                | ✅    |
| `useReadinessText.ts`                         | 辅助 | 就绪度发现的本地化措辞 SSOT：按后端稳定 `code` + `names/count` 取 `Agent.readiness.reasons.*`；后端英文 `reason`/`next_action` 仅作诊断、从不展示；未知 `code` 回退按等级的通用句、未知维度回退「其他」，长名单只列前 3 项；列表与输入框徽标共用 | ✅    |
| `__tests__/agentEditFormModel.test.ts`        | 核心 | 表单模型单测：zod 边界、详情回填默认值、载荷 null 规则、命令绑定过滤、验收清单裁剪、回填→载荷往返                                                                                                                                                | ✅    |
| `__tests__/AgentEditForm.test.tsx`            | 核心 | 表单集成单测：新建/编辑提交载荷、校验错误（`text-destructive-text`）、保存失败 toast、提交中禁用、切换到新建时字段全部重置                                                                                                                        | ✅    |
| `__tests__/AgentEditAvatarField.test.tsx`     | 核心 | 头像区段单测：图标高亮与选择、文件选择打开、新建仅预览、已保存上传成功/失败、上传中旋转图标                                                                                                                                                      | ✅    |
| `__tests__/AgentEditSections.test.tsx`        | 核心 | 责任 / 浏览器 / 会话策略区段单测：各字段 patch、风险提示、24 个 UTC 小时、空闲分钟钳位                                                                                                                                                            | ✅    |
| `__tests__/AgentSettingsPreviewGate.test.tsx` | 核心 | 预览门控单测：覆盖 5 维设置矩阵完整渲染、空配置回退文案、团队徽章、返回导航与确认创建按钮回调及禁用状态                                                                                                                                          | ✅    |

## 消费方（示例）

- `features/chat-window/` — `AgentBrickCard`、`AgentInfoBanner`、`AgentIndicator`
- `features/settings/sections/ai-core/` — `AgentsSection`
- `features/cron/` — 定时任务智能体展示
- `app/agents/page.tsx` — 智能体管理页
- `layout/AgentSidebarContent.tsx` — 侧栏智能体列表
- `lib/utils/avatarUtils.ts` — 头像 URL 解析（引用 `AGENT_ICON_REGISTRY`）

## 依赖

- `@/components/primitives/*`
- `@/lib/utils/*`
- 父模块 [`components/_ARCH.md`](../_ARCH.md)
