# chat-window/conversational-config/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ConversationalConfigActionCard.tsx` | 组件 | 导出 `ConversationalConfigActionCard` | — |
| `NonDevZeroFrictionWizardModal.tsx` | 组件 | 导出 `NonDevZeroFrictionWizardModal` | — |
| `conversationalConfigEngine.ts` | 引擎 | 导出 `maskSecretKey`、`parseNaturalLanguageConfigIntent`、`validateConfigParams` | — |
| `conversationalConfigTypes.ts` | 类型 | 导出类型 `ConfigIntentCategory`、`ConfigParamItem`、`ConversationalConfigIntent`、`NonDevWizardStep` | — |
| `index.ts` | 入口 | 聚合导出 `./conversationalConfigTypes`、`./conversationalConfigEngine`、`./useConversationalConfigStore`、`./ConversationalConfigActionCard`、`./NonDevZeroFrictionWizardModal` | — |
| `useConversationalConfigStore.ts` | 状态仓库 | 导出 `NON_DEV_WIZARD_STEPS`、`useConversationalConfigStore` | — |
| `__tests__/ConversationalConfigActionCard.test.tsx` | 测试 | `ConversationalConfigActionCard`；5 个用例 | — |
| `__tests__/NonDevZeroFrictionWizardModal.test.tsx` | 测试 | `NonDevZeroFrictionWizardModal`；5 个用例 | — |
| `__tests__/conversationalConfigEngine.test.ts` | 测试 | `conversationalConfigEngine`；10 个用例 | — |
| `__tests__/useConversationalConfigStore.test.ts` | 测试 | `useConversationalConfigStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
