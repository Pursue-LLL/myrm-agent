# app-shell/keyboard-nav/

## 架构概述

7 个源文件（2 个组件、1 个入口、1 个引擎、1 个类型、2 个Hook），5 个测试文件；`index.ts` 是对外入口。

现状：本目录下的模块都没有从产品入口可达的导入（`bun run verify:orphans` 把它们列为孤儿）；接入产品入口或删除目录时，同步更新本文件。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `AccessibleNavigableModelList.tsx` | 组件 | 导出 `AccessibleNavigableModelList`；类型 `AccessibleNavigableModelListProps` | — |
| `OverflowTabStripContainer.tsx` | 组件 | 导出 `OverflowTabStripContainer`；类型 `TabItem`、`OverflowTabStripContainerProps` | — |
| `index.ts` | 入口 | 聚合导出 `./modelPickerKeyboardTypes`、`./modelPickerKeyboardEngine`、`./useModelPickerKeyboardNav`、`./useTabStripReveal`、`./AccessibleNavigableModelList`、`./OverflowTabStripContainer` | — |
| `modelPickerKeyboardEngine.ts` | 引擎 | 导出 `DEFAULT_TAB_SAFE_MARGIN_PX`、`getNextNavIndex`、`calculateScrollRevealOffset`、`detectTabStripOverflow`、`formatAriaActiveDescendantId` | — |
| `modelPickerKeyboardTypes.ts` | 类型 | 导出类型 `NavigableModelItem`、`KeyboardNavDirection`、`DOMRectLike`、`TabStripOverflowState`、`TabRevealOptions` | — |
| `useModelPickerKeyboardNav.ts` | Hook | 导出 `useModelPickerKeyboardNav`；类型 `UseModelPickerKeyboardNavOptions` | — |
| `useTabStripReveal.ts` | Hook | 导出 `useTabStripReveal`；类型 `UseTabStripRevealOptions` | — |
| `__tests__/AccessibleNavigableModelList.test.tsx` | 测试 | `AccessibleNavigableModelList`；5 个用例 | — |
| `__tests__/modelPickerKeyboardEngine.test.ts` | 测试 | `modelPickerKeyboardEngine`；10 个用例 | — |
| `__tests__/modelPickerKeyboardIntegration.test.tsx` | 测试 | `ModelPickerKeyboard & OverflowTabStrip Integration`；1 个用例 | — |
| `__tests__/useModelPickerKeyboardNav.test.ts` | 测试 | `useModelPickerKeyboardNav`；6 个用例 | — |
| `__tests__/useTabStripReveal.test.ts` | 测试 | `useTabStripReveal`；3 个用例 | — |

## 依赖

- 第三方：`lucide-react`、`react`
