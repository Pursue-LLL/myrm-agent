# markdown-render-tools/

## 架构概述

Markdown 渲染扩展与工具块展示。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CodeBlock.tsx` | 组件/模块 | — | — |
| `InlineDiffViewer.tsx` | 组件/模块 | — | — |
| `InlineHtmlWidget.tsx` | 组件/模块 | — | — |
| `LinkPopover.tsx` | 组件/模块 | — | — |
| `MarkdownImage.tsx` | 组件/模块 | — | — |
| `MathRenderer.tsx` | 组件/模块 | — | — |
| `MermaidChart.tsx` | 组件/模块 | — | — |
| `MermaidLegendPanel.tsx` | 组件/模块 | — | — |
| `ThinkBox.tsx` | 组件/模块 | — | — |
| `ThinkTagProcessor.tsx` | 组件/模块 | — | — |
| `mermaid-theme.ts` | 组件/模块 | — | — |
| `rehypeHeadingIds.ts` | 组件/模块 | — | — |

## 依赖

- `@/lib/diff/DiffViewer`（共享 Diff 可视化组件，InlineDiffViewer 为薄包装层）
- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
