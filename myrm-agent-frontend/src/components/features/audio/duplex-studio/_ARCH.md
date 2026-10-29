# audio/duplex-studio/

## 架构概述

7 个源文件（3 个组件、1 个引擎、1 个类型、1 个入口、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BargeInFeedbackBanner.tsx` | 组件 | 导出 `BargeInFeedbackBanner`；类型 `BargeInFeedbackBannerProps` | — |
| `DuplexAudioWaveformVisualizer.tsx` | 组件 | 导出 `DuplexAudioWaveformVisualizer`；类型 `DuplexAudioWaveformVisualizerProps` | — |
| `HandsFreeDuplexStudioCard.tsx` | 组件 | 导出 `HandsFreeDuplexStudioCard`；类型 `HandsFreeDuplexStudioCardProps` | — |
| `duplexVoiceEngine.ts` | 引擎 | 导出 `getBargeInVolumeThreshold`、`shouldTriggerBargeIn`、`healContextOnBargeIn`、`finalizeInterruptedTurn`、`normalizeWaveformHeights` | — |
| `duplexVoiceTypes.ts` | 类型 | 导出类型 `DuplexSessionStatus`、`BargeInSensitivity`、`BargeInState`、`AudioChannelMetrics`、`DuplexTurnMessage`、`DuplexSettings` 等 7 个 | — |
| `index.ts` | 入口 | 聚合导出 `./duplexVoiceTypes`、`./duplexVoiceEngine`、`./useDuplexVoiceStore`、`./DuplexAudioWaveformVisualizer`、`./BargeInFeedbackBanner`、`./HandsFreeDuplexStudioCard` | — |
| `useDuplexVoiceStore.ts` | 状态仓库 | 导出 `useDuplexVoiceStore`；类型 `DuplexVoiceActions`、`DuplexVoiceStore` | — |
| `__tests__/BargeInFeedbackBanner.test.tsx` | 测试 | `BargeInFeedbackBanner`；3 个用例 | — |
| `__tests__/DuplexAudioWaveformVisualizer.test.tsx` | 测试 | `DuplexAudioWaveformVisualizer`；3 个用例 | — |
| `__tests__/duplexVoiceEngine.test.ts` | 测试 | `duplexVoiceEngine`；6 个用例 | — |
| `__tests__/duplexVoiceIntegration.test.tsx` | 测试 | `DuplexVoice Integration End-to-End`；3 个用例 | — |
| `__tests__/useDuplexVoiceStore.test.ts` | 测试 | `useDuplexVoiceStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
