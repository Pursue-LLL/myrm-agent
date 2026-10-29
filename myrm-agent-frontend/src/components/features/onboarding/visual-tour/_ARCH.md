# onboarding/visual-tour/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个状态仓库、1 个引擎、1 个类型），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `InteractiveFeatureSpotlightTour.tsx` | 组件 | 导出 `InteractiveFeatureSpotlightTour` | — |
| `QuickStartChecklistCard.tsx` | 组件 | 导出 `QuickStartChecklistCard` | — |
| `RealPlaygroundTemplateDeck.tsx` | 组件 | 导出 `RealPlaygroundTemplateDeck`；类型 `RealPlaygroundTemplateDeckProps` | — |
| `index.ts` | 入口 | 聚合导出 `./visualTourTypes`、`./visualTourEngine`、`./useVisualTourStore`、`./InteractiveFeatureSpotlightTour`、`./QuickStartChecklistCard`、`./RealPlaygroundTemplateDeck` | — |
| `useVisualTourStore.ts` | 状态仓库 | 导出 `useVisualTourStore`；类型 `VisualTourState` | — |
| `visualTourEngine.ts` | 引擎 | 导出 `DEFAULT_TOUR_STEPS`、`DEFAULT_CHECKLIST_ITEMS`、`DEFAULT_PLAYGROUND_TEMPLATES`、`calculateSpotlightRect`、`calculateChecklistProgress`、`buildSandboxExecutionPayload` 等 8 个 | — |
| `visualTourTypes.ts` | 类型 | 导出类型 `SpotlightPlacement`、`TourStep`、`ChecklistItem`、`PlaygroundTemplate`、`SpotlightRect`、`ChecklistProgress` 等 7 个 | — |
| `__tests__/InteractiveFeatureSpotlightTour.test.tsx` | 测试 | `InteractiveFeatureSpotlightTour`；5 个用例 | — |
| `__tests__/QuickStartChecklistCard.test.tsx` | 测试 | `QuickStartChecklistCard`；6 个用例 | — |
| `__tests__/useVisualTourStore.test.ts` | 测试 | `useVisualTourStore`；7 个用例 | — |
| `__tests__/visualTourEngine.test.ts` | 测试 | `visualTourEngine`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
