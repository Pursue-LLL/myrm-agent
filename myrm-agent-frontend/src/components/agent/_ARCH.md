# components/agent/

## 架构概述

跨 feature 共用的智能体 UI 原语（头像、图标、就绪度列表、记忆容量看板、内置智能体 i18n）。智能体的创建与编辑只在设置页（`settings/.../AgentsSection` → `AgentEditPanel`），本目录只放可复用的展示组件。

## 文件清单

| 文件                         | 地位 | 职责                                                                                                                                                                                                                                             | I/O/P |
| ---------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----- |
| `AgentAvatar.tsx`            | 核心 | 智能体头像（icon/lucide/emoji/image/首字母）                                                                                                                                                                                                     | ✅    |
| `agent-icons.tsx`            | 核心 | 内置智能体 SVG 图标注册表与 `AgentIcon`                                                                                                                                                                                                          | ✅    |
| `lucide-icon-resolver.tsx`   | 核心 | 按名称（kebab/PascalCase）解析 Lucide 图标：`findLucideIcon`（未知返回 null）/`resolveLucideIcon`（回退 Bot），每个图标经 `DynamicIcon` 异步加载自己的 chunk；禁止 `import * as` 整库引入                                                        |
| `builtin-agent-i18n-data.ts` | 核心 | 内置智能体 i18n 数据 SSOT（key 须与 server `_BUILTIN_AGENTS` id 一一对应；`__tests__/builtin-agent-i18n-data.test.ts` + server `test_builtin_agent_i18n_parity.py` 守护）                                                                        | ✅    |
| `builtin-agent-i18n.ts`      | 核心 | 内置智能体 locale 解析（getBuiltinAgentName/Description）                                                                                                                                                                                        | ✅    |
| `DualLayerMemoryCard.tsx`    | 核心 | 用户画像与智能体工作笔记双层结构化看板（USER / MEMORY 两层容量水位指示器与垃圾记忆准入探针）；全部文案取自 `memory.dualLayer` 六语言命名空间                                                                                                     | ✅    |
| `WatermarkBar.tsx`           | 辅助 | 单层记忆容量水位条（已用 / 上限字符、等级徽标、服务端告警）与 `levelForRatio`（编辑中按 70% / 90% / 100% 阈值本地推导等级，与服务端一致）；文案取自 `memory.dualLayer`                                                                           | ✅    |
| `AgentReadinessList.tsx`     | 辅助 | 就绪度逐项列表（文案来自 `useReadinessText`），为未就绪项提供设置深链；插件导入结果页使用                                                                                                                                                        | ✅    |
| `useReadinessText.ts`        | 辅助 | 就绪度发现的本地化措辞 SSOT：按后端稳定 `code` + `names/count` 取 `Agent.readiness.reasons.*`；后端英文 `reason`/`next_action` 仅作诊断、从不展示；未知 `code` 回退按等级的通用句、未知维度回退「其他」，长名单只列前 3 项；列表与输入框徽标共用 | ✅    |

## 消费方（示例）

- `features/chat-window/` — `AgentInfoBanner`
- `features/message-input-actions/` — `AgentIndicator`
- `features/settings/sections/ai-core/` — `AgentsSection`
- `features/cron/` — 定时任务智能体展示
- `features/plugins/` — `PluginImportResult`（就绪度列表）
- `lib/utils/avatarUtils.ts` — 头像 URL 解析（引用 `AGENT_ICON_REGISTRY`）

## 依赖

- `@/components/primitives/*`
- `@/lib/utils/*`
- 父模块 [`components/_ARCH.md`](../_ARCH.md)
