# markdown-render-tools/

## 架构概述

Markdown 渲染扩展与工具块展示。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `CodeBlock.tsx` | 组件/模块 | 见源码 | 见源码 |
| `InlineDiffViewer.tsx` | 组件/模块 | 见源码 | 见源码 |
| `InlineHtmlWidget.tsx` | 组件/模块 | 见源码 | 见源码 |
| `LinkPopover.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MarkdownImage.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MathRenderer.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MermaidChart.tsx` | 组件/模块 | 见源码 | 见源码 |
| `MermaidLegendPanel.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ThinkBox.tsx` | 组件/模块 | 见源码 | 见源码 |
| `ThinkTagProcessor.tsx` | 组件/模块 | 见源码 | 见源码 |
| `hooks/` | 目录 | 子模块 | 见源码 |
| `mermaid-theme.ts` | 组件/模块 | 见源码 | 见源码 |
| `rehypeHeadingIds.ts` | 组件/模块 | 见源码 | 见源码 |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
