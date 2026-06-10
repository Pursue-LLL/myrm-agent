# lib/diff/

## 架构概述

unified diff 纯函数解析（无 React 依赖）。Hook 封装见 `src/hooks/useDiffParser.ts`。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `parseUnifiedDiff.ts` | 核心 | unified diff 类型与纯函数解析 | ✅ |
| `__tests__/parseUnifiedDiff.test.ts` | 测试 | 空结果隔离、hunk/CRLF/binary/deleted-file | — |

## 消费方

- `hooks/useDiffParser.ts`
- `features/cli-visualization/CLIDiffViewer.tsx`
- `features/markdown-render-tools/InlineDiffViewer.tsx`
