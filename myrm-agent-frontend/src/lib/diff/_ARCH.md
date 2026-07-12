# lib/diff/

## 架构概述

unified diff 解析与可视化。纯函数解析器无 React 依赖，DiffViewer 为共享可视化组件。Hook 封装见 `src/hooks/useDiffParser.ts`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `parseUnifiedDiff.ts` | 核心 | unified diff 解析、Split 配对算法、语言推断（纯函数，无 React 依赖） | ✅ |
| `DiffViewer.tsx` | 核心 | 共享 Diff 可视化组件（Unified/Split 视图、Prism 语法高亮） | ✅ |
| `__tests__/parseUnifiedDiff.test.ts` | 测试 | 覆盖 new-file、multi-hunk、`---/+++` 回退等解析分支 | ✅ |

## 消费方

- `hooks/useDiffParser.ts`
- `features/cli-visualization/CLIDiffViewer.tsx`（薄包装，透传 DiffViewer）
- `features/markdown-render-tools/InlineDiffViewer.tsx`（薄包装，透传 DiffViewer）
