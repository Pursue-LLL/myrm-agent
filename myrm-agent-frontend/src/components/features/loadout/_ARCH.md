# loadout/

## 架构概述

Agent Loadout 与 Team Assets 导航编排层：组合现有 memory/wiki/skills/shared-context 组件与 API，不复制 SSOT 表单或审核逻辑。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AgentLoadoutSummary.tsx` | 核心 | 单 Agent 配装摘要（SC/Skills/Wiki/Memory/Readiness）+ 深链；`#loadout` hash 滚动 | ✅ |
| `TeamAssetsHub.tsx` | 核心 | 团队资产一屏：嵌入 SharedContextPanel + Wiki/Skills/Memory 入口卡片 + 全局资产状态摘要 + 跨 Agent readiness 巡检速览（内置 Agent 徽标 + `getBuiltinAgentName` 名称本地化） | ✅ |
| `useTeamAssetsHubSummary.ts` | 辅助 | 团队级资产摘要编排：并行拉取 skills 总数 / 待审核记忆数 / 各 agent readiness 速览（含 `is_built_in` 标识）+ 全局 memory 策略；源失败时返回 `unavailable` 避免假 0/假 Ready，无新增后端聚合 API | ✅ |
| `useAgentLoadoutSummary.ts` | 辅助 | 并行拉取 agent/readiness/SC bindings/proposals + 全局 memory 策略；bindings/proposals/readiness 失败时返回 `unavailable` 避免假 0/假 None/假 Ready；`refreshKey` 驱动 bind/unbind 与保存后重拉 | ✅ |
| `loadoutDeepLinks.ts` | 辅助 | Settings URL SSOT 深链常量 · `#loadout` · `#shared-context-binding` 锚点 | ✅ |
| `__tests__/TeamAssetsHub.test.tsx` | 测试 | Vitest 摘要卡 / badge / readiness 速览 / 深链 / 加载态断言 | — |
| `__tests__/useTeamAssetsHubSummary.test.ts` | 测试 | Vitest 汇总聚合、源 `unavailable` 态、agent 速览构造断言 | — |
| `__tests__/AgentLoadoutSummary.test.tsx` | 测试 | Vitest 渲染、team assets 深链、unavailable 态断言 | — |
| `__tests__/useAgentLoadoutSummary.test.ts` | 测试 | refreshKey 变更触发 reload 回归 | — |

## 依赖

- `@/components/features/memory/SharedContextPanel`
- `@/services/agent` · `@/services/memorySharedContexts`
- `@/services/skill` · `@/services/memory`
- `@/store/useConfigStore`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)

## 产品入口

- `AgentCapabilitiesTab` 嵌入 `AgentLoadoutSummary`（`AgentEditPanel` 识别 `#loadout` 切换 capabilities Tab）
- `/agents` 卡片 → `/settings/agents?agentId=#loadout`
- Migration Wizard Result → `/settings/memory?sub=team-hub` · agent loadout 深链
- Memory Center tab `team-hub` · SettingsMenu memory 子项 `team-hub`
- Team template instantiate → `TemplateMarket` 深链 team hub / agent loadout
