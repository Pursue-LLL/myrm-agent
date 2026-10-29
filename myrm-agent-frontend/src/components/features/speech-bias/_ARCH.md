# speech-bias/

## 架构概述

6 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `DevLexiconBiasDrawer.tsx` | 组件 | 导出 `DevLexiconBiasDrawer`；类型 `DevLexiconBiasDrawerProps` | — |
| `VoiceDevConfirmCard.tsx` | 组件 | 导出 `VoiceDevConfirmCard`；类型 `VoiceDevConfirmCardProps` | — |
| `index.ts` | 入口 | 聚合导出 `./speechBiasTypes`、`./speechBiasEngine`、`./useSpeechBiasStore`、`./VoiceDevConfirmCard`、`./DevLexiconBiasDrawer` | — |
| `speechBiasEngine.ts` | 引擎 | 导出 `DEFAULT_DEV_LEXICON`、`extractContextTerms`、`correctSpeechTranscript`、`detectAndFormatCodeSymbols`；类型 `ContextExtractionInput` | — |
| `speechBiasTypes.ts` | 类型 | 导出类型 `DevTermCategory`、`DevTermItem`、`CorrectionRecord`、`CorrectionResult`、`DictationStatus`、`SpeechBiasState` | — |
| `useSpeechBiasStore.ts` | 状态仓库 | 导出 `useSpeechBiasStore`；类型 `SpeechBiasActions`、`SpeechBiasStore` | — |
| `__tests__/DevLexiconBiasDrawer.test.tsx` | 测试 | `DevLexiconBiasDrawer`；5 个用例 | — |
| `__tests__/VoiceDevConfirmCard.test.tsx` | 测试 | `VoiceDevConfirmCard`；5 个用例 | — |
| `__tests__/speechBiasEngine.test.ts` | 测试 | `speechBiasEngine`；5 个用例 | — |
| `__tests__/speechBiasIntegration.test.ts` | 测试 | `speechBiasIntegration`；2 个用例 | — |
| `__tests__/useSpeechBiasStore.test.ts` | 测试 | `useSpeechBiasStore`；6 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
