# chat-window/pacing-selector/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ModelPacingDetailPopover.tsx` | 组件 | Implementation for Item 191 detailed selector popover. Allows users to switch between Fast (<5s) / Balanced (10-25s) / Smart (30-90s). | ✅ |
| `ModelPacingSelectorPill.tsx` | 组件 | Implementation for Item 191 input bar pill. Provides instant one-click inspection and tier switching between Fast / Balanced / Smart. | ✅ |
| `index.ts` | 入口 | Public entrypoint for model execution pacing types, engine, store, selector pill, and popover. | ✅ |
| `modelPacingEngine.ts` | 引擎 | Pure computation engine for Item 191: TriTierModelExecutionPacingSelectorAndP1LatencyPresetSuite. Maps abstract execution pacing tiers (fast/balanced/smart) to concrete execution specs, latency budgets, and provides smart heuristics for prompt analysis. | ✅ |
| `modelPacingTypes.ts` | 类型 | Unified contract for Item 191: TriTierModelExecutionPacingSelectorAndP1LatencyPresetSuite. Abstracting complex model matrices into three intuitive execution speeds: Fast (Daily P1 low-latency) / Balanced (Everyday dev) / Smart (Deep reasoning & audit). | ✅ |
| `useModelPacingStore.ts` | 状态仓库 | Central reactive dispatcher for Item 191. Governs execution pacing (fast/balanced/smart) and synchronizes with downstream chat store optimizationMode. | ✅ |
| `__tests__/ModelPacingDetailPopover.test.tsx` | 测试 | `ModelPacingDetailPopover`；4 个用例 | — |
| `__tests__/ModelPacingSelectorPill.test.tsx` | 测试 | `ModelPacingSelectorPill`；5 个用例 | — |
| `__tests__/modelPacingEngine.test.ts` | 测试 | `modelPacingEngine`；8 个用例 | — |
| `__tests__/modelPacingTypes.test.ts` | 测试 | `modelPacingTypes`；3 个用例 | — |
| `__tests__/useModelPacingStore.test.ts` | 测试 | `useModelPacingStore`；5 个用例 | — |

## 依赖

- 项目内：`@/store/useChatStore`
- 第三方：`lucide-react`、`react`、`zustand`
