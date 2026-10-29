# companion/speech-loop/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `MiniApprovalDrawer.tsx` | 组件 | 导出 `MiniApprovalDrawer`；类型 `MiniApprovalDrawerProps` | — |
| `PetLoopStageBadge.tsx` | 组件 | 导出 `PetLoopStageBadge`；类型 `PetLoopStageBadgeProps` | — |
| `PetSpeechLoopOverlay.tsx` | 组件 | 导出 `PetSpeechLoopOverlay`；类型 `PetSpeechLoopOverlayProps` | — |
| `index.ts` | 入口 | 聚合导出 `./petSpeechLoopTypes`、`./petSpeechLoopEngine`、`./usePetSpeechLoopStore`、`./PetLoopStageBadge`、`./MiniApprovalDrawer`、`./PetSpeechLoopOverlay` | — |
| `petSpeechLoopEngine.ts` | 引擎 | 导出 `decomposeSpeechPrompt`、`derivePetMoodByPhase`、`deriveBubbleMessage`、`buildApprovalActionPayload`、`advanceStepStage` | — |
| `petSpeechLoopTypes.ts` | 类型 | 导出类型 `LoopPhase`、`PetMood`、`VoiceCaptureStatus`、`StepStatus`、`FourStagePhase`、`LoopTaskStep` 等 9 个 | — |
| `usePetSpeechLoopStore.ts` | 状态仓库 | 导出 `usePetSpeechLoopStore`；类型 `PetSpeechLoopActions`、`PetSpeechLoopStore` | — |
| `__tests__/MiniApprovalDrawer.test.tsx` | 测试 | `MiniApprovalDrawer`；6 个用例 | — |
| `__tests__/PetLoopStageBadge.test.tsx` | 测试 | `PetLoopStageBadge`；3 个用例 | — |
| `__tests__/petSpeechLoopEngine.test.ts` | 测试 | `petSpeechLoopEngine`；6 个用例 | — |
| `__tests__/petSpeechLoopIntegration.test.tsx` | 测试 | `PetSpeechLoop Integration End-to-End`；2 个用例 | — |
| `__tests__/usePetSpeechLoopStore.test.ts` | 测试 | `usePetSpeechLoopStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
