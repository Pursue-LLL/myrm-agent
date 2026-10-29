# floating-pet/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CompanionFloatingPet.tsx` | 组件 | 导出 `CompanionFloatingPet`；类型 `CompanionFloatingPetProps` | — |
| `MiniTaskBubble.tsx` | 组件 | 导出 `MiniTaskBubble`；类型 `MiniTaskBubbleProps` | — |
| `floatingPetEngine.ts` | 引擎 | 导出 `computePetMood`、`getPetGlowStyle`、`formatVoiceTranscriptToTask`、`calculateDockPositionClasses`；类型 `PetGlowStyle` | — |
| `floatingPetTypes.ts` | 类型 | 导出类型 `PetMoodState`、`PetDockPosition`、`PetTaskItem`、`FloatingPetState` | — |
| `index.ts` | 入口 | 聚合导出 `./floatingPetTypes`、`./floatingPetEngine`、`./useFloatingPetStore`、`./CompanionFloatingPet`、`./MiniTaskBubble` | — |
| `useFloatingPetStore.ts` | 状态仓库 | 导出 `useFloatingPetStore`；类型 `FloatingPetActions`、`FloatingPetStore` | — |
| `__tests__/CompanionFloatingPet.test.tsx` | 测试 | `CompanionFloatingPet`；4 个用例 | — |
| `__tests__/MiniTaskBubble.test.tsx` | 测试 | `MiniTaskBubble`；5 个用例 | — |
| `__tests__/floatingPetEngine.test.ts` | 测试 | `floatingPetEngine`；4 个用例 | — |
| `__tests__/floatingPetIntegration.test.ts` | 测试 | `floatingPetIntegration`；1 个用例 | — |
| `__tests__/useFloatingPetStore.test.ts` | 测试 | `useFloatingPetStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
