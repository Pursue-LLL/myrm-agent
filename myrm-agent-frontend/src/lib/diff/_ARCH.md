# lib/diff/

## 架构概述

unified diff 解析与可视化。纯函数解析器无 React 依赖，DiffViewer 为共享可视化组件。Hook 封装见 `src/hooks/shared/useDiffParser.ts`。

## 文件清单

| 文件                                 | 地位 | 职责                                                                                                                                                                                               | I/O/P |
| ------------------------------------ | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `parseUnifiedDiff.ts`                | 核心 | unified diff 解析、Split 配对算法、语言推断（纯函数，无 React 依赖；导出 `EXT_TO_LANGUAGE` 扩展名映射，其中每个语言都必须在 `lib/syntax/prism` 里有语法，scss 因此不在表内）；hunk 头声明的行数没用完时，所有行都按正文读（被删的 `---`、新增的 `++i;` 不会被当成文件头），diff 结尾的换行不产生多余的空行 | ✅    |
| `DiffViewer.tsx`                     | 核心 | 共享 Diff 可视化组件（Unified/Split 视图、Prism 语法高亮，语法与语言判定来自 `lib/syntax/prism`，一行超过 10,000 字符时该行保持纯文本；支持 `embedded` 内联模式；hunk 头单行显示不折行）                                                                                        | ✅    |
| `TextDiffViewer.tsx`                 | 核心 | 基于 `createPatch` 的纯文本 old/new 对比薄包装；对比有 500 ms 耗时上限，整篇重写之类算不完的改动不渲染 diff，只用 `common.diffTooLarge`（`role=status`）说明两侧行数                               | ✅    |
| `__tests__/parseUnifiedDiff.test.ts` | 测试 | 覆盖 new-file、multi-hunk、`---/+++` 回退等解析分支，以及 hunk 正文：结尾换行、被删 `---`、新增 `++i;`、正文里的 `Binary files`、第二个文件的文件头、`\ No newline` 标记、行数写少的 hunk 头       | ✅    |
| `__tests__/TextDiffViewer.test.tsx`  | 测试 | 纯文本 old/new diff 渲染；整篇重写在耗时上限内退化为带两侧行数的说明（末尾换行不算一行）                                                                                                           | ✅    |

## 消费方

- `hooks/shared/useDiffParser.ts`
- `features/markdown-render-tools/InlineDiffViewer.tsx`（薄包装，透传 DiffViewer）
