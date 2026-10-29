# workspace/visual-theming/

## 架构概述

7 个源文件（3 个组件、1 个入口、1 个状态仓库、1 个引擎、1 个类型），4 个测试文件；`index.ts` 是对外入口。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `DualWorkModeToggleSwitcher.tsx` | 组件 | 导出 `DualWorkModeToggleSwitcher` | — |
| `ModeAdaptivePromptDeck.tsx` | 组件 | 导出 `ModeAdaptivePromptDeck` | — |
| `WorkspaceVisualIdentityPickerModal.tsx` | 组件 | 导出 `WorkspaceVisualIdentityPickerModal` | — |
| `index.ts` | 入口 | 聚合导出 `./workspaceThemingTypes`、`./workspaceThemingEngine`、`./useWorkspaceThemingStore`、`./DualWorkModeToggleSwitcher`、`./WorkspaceVisualIdentityPickerModal`、`./ModeAdaptivePromptDeck` | — |
| `useWorkspaceThemingStore.ts` | 状态仓库 | 导出 `INITIAL_PRESET_WORKSPACES`、`useWorkspaceThemingStore` | — |
| `workspaceThemingEngine.ts` | 引擎 | 导出 `getColorClasses`、`getModeAdaptiveSuggestions`、`validateWorkspaceTheme`、`formatWorkspaceBreadcrumb`；类型 `ThemeColorClasses` | — |
| `workspaceThemingTypes.ts` | 类型 | 导出类型 `WorkMode`、`WorkspaceThemeColor`、`WorkspaceSemanticIcon`、`WorkspaceVisualTheme`、`WorkspaceItem`、`ModeAdaptiveSuggestion` | — |
| `__tests__/DualWorkModeToggleSwitcher.test.tsx` | 测试 | `DualWorkModeToggleSwitcher`；3 个用例 | — |
| `__tests__/WorkspaceVisualIdentityPickerModal.test.tsx` | 测试 | `WorkspaceVisualIdentityPickerModal`；4 个用例 | — |
| `__tests__/useWorkspaceThemingStore.test.ts` | 测试 | `useWorkspaceThemingStore`；5 个用例 | — |
| `__tests__/workspaceThemingEngine.test.ts` | 测试 | `workspaceThemingEngine`；8 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`、`zustand`
