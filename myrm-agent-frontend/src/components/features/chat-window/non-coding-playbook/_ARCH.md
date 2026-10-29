# chat-window/non-coding-playbook/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `NonCodingPlaybookGallery.tsx` | 组件 | 导出 `NonCodingPlaybookGallery` | — |
| `PlaybookPrefillModal.tsx` | 组件 | 导出 `PlaybookPrefillModal` | — |
| `WhyAgentOverRawChatModal.tsx` | 组件 | 导出 `WhyAgentOverRawChatModal` | — |
| `index.ts` | 入口 | 聚合导出 `./nonCodingPlaybookTypes`、`./nonCodingPlaybookEngine`、`./useNonCodingPlaybookStore`、`./NonCodingPlaybookGallery`、`./PlaybookPrefillModal`、`./WhyAgentOverRawChatModal` | — |
| `nonCodingPlaybookEngine.ts` | 引擎 | 导出 `generatePrefilledPrompt`、`filterPlaybooksByCategory`、`searchPlaybooks`、`getCategoryMeta`、`STATIC_COMPARISON_FEATURES` | — |
| `nonCodingPlaybookTypes.ts` | 类型 | 导出类型 `PlaybookCategory`、`ParameterFieldType`、`PlaybookParameterField`、`PlaybookScenario`、`ComparisonFeature` | — |
| `useNonCodingPlaybookStore.ts` | 状态仓库 | 导出 `INITIAL_PRESET_SCENARIOS`、`useNonCodingPlaybookStore` | — |
| `__tests__/NonCodingPlaybookGallery.test.tsx` | 测试 | `NonCodingPlaybookGallery`；5 个用例 | — |
| `__tests__/PlaybookPrefillModal.test.tsx` | 测试 | `PlaybookPrefillModal`；5 个用例 | — |
| `__tests__/nonCodingPlaybookEngine.test.ts` | 测试 | `nonCodingPlaybookEngine`；8 个用例 | — |
| `__tests__/useNonCodingPlaybookStore.test.ts` | 测试 | `useNonCodingPlaybookStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
