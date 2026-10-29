# clarification-questionnaire/

## 架构概述

6 个源文件（2 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ClarificationQuestionnaireCard.tsx` | 组件 | 导出 `ClarificationQuestionnaireCard`；类型 `ClarificationQuestionnaireCardProps` | — |
| `V1SpecSummaryModal.tsx` | 组件 | 导出 `V1SpecSummaryModal`；类型 `V1SpecSummaryModalProps` | — |
| `clarificationQuestionnaireEngine.ts` | 引擎 | 导出 `DEFAULT_CLARIFICATION_QUESTIONS`、`parseQuestionOption`、`autoApplyAllRecommendations`、`synthesizeV1Spec`、`isQuestionnaireReadyToSubmit`；类型 `ReadyCheckResult` | — |
| `clarificationQuestionnaireTypes.ts` | 类型 | 导出类型 `QuestionOption`、`ClarificationAttachment`、`QuestionnaireQuestion`、`V1SpecContract`、`QuestionnaireStatus`、`ClarificationQuestionnaireState` | — |
| `index.ts` | 入口 | 聚合导出 `./clarificationQuestionnaireTypes`、`./clarificationQuestionnaireEngine`、`./useClarificationQuestionnaireStore`、`./ClarificationQuestionnaireCard`、`./V1SpecSummaryModal` | — |
| `useClarificationQuestionnaireStore.ts` | 状态仓库 | 导出 `useClarificationQuestionnaireStore`；类型 `ClarificationQuestionnaireActions`、`ClarificationQuestionnaireStore` | — |
| `__tests__/ClarificationQuestionnaireCard.test.tsx` | 测试 | `ClarificationQuestionnaireCard`；6 个用例 | — |
| `__tests__/V1SpecSummaryModal.test.tsx` | 测试 | `V1SpecSummaryModal`；4 个用例 | — |
| `__tests__/clarificationQuestionnaireEngine.test.ts` | 测试 | `clarificationQuestionnaireEngine`；5 个用例 | — |
| `__tests__/clarificationQuestionnaireIntegration.test.ts` | 测试 | `clarificationQuestionnaireIntegration`；1 个用例 | — |
| `__tests__/useClarificationQuestionnaireStore.test.ts` | 测试 | `useClarificationQuestionnaireStore`；5 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
