# chat-window/modal-editor/

## 架构概述

5 个源文件（1 个组件、1 个入口、1 个引擎、1 个类型、1 个状态仓库），5 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `PopoutFullscreenModalEditor.tsx` | 组件 | Primary modal UI for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite. Resolves long-form PRDs, logs, and multi-paragraph prompts via pop-out modal composing (Ctrl+G). | ✅ |
| `index.ts` | 入口 | Public barrel export module for pop-out fullscreen modal Markdown editor & desktop bridge. | ✅ |
| `modalEditorEngine.ts` | 引擎 | Pure computation engine for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite. Analyzes word/char/line metrics, provides standardized writing templates, and bridges desktop external editor events. | ✅ |
| `modalEditorTypes.ts` | 类型 | Unified types for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite. Supports pop-out fullscreen Markdown composing, word/line analytics, template insertion, and Tauri external desktop editor bridges (Ctrl+G). | ✅ |
| `useModalEditorStore.ts` | 状态仓库 | Central reactive dispatcher for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite. Manages modal editor draft content, clean dismissal, template insertions, and desktop external editor bridge synchronization. | ✅ |
| `__tests__/PopoutFullscreenModalEditor.test.tsx` | 测试 | `PopoutFullscreenModalEditor`；8 个用例 | — |
| `__tests__/modalEditorEngine.test.ts` | 测试 | `modalEditorEngine`；7 个用例 | — |
| `__tests__/modalEditorIntegration.test.ts` | 测试 | `modalEditorIntegration`；3 个用例 | — |
| `__tests__/modalEditorTypes.test.ts` | 测试 | `modalEditorTypes`；1 个用例 | — |
| `__tests__/useModalEditorStore.test.ts` | 测试 | `useModalEditorStore`；7 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
