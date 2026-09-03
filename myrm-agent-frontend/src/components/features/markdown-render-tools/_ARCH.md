# markdown-render-tools/

## 架构概述

Markdown 渲染扩展与工具块展示。

## 文件清单

| 文件                     | 地位 | 职责                                                                                                   | I/O/P |
| ------------------------ | ---- | ------------------------------------------------------------------------------------------------------ | ----- |
| `CodeBlock.tsx`          | 核心 | fenced code block：语法高亮、复制按钮、语言标签                                                        | ✅    |
| `InlineDiffViewer.tsx`   | 核心 | 行内 unified diff 预览（薄包装 `lib/diff/DiffViewer`）                                                 | ✅    |
| `InlineHtmlWidget.tsx`   | 核心 | 沙箱化 inline HTML widget iframe 渲染                                                                  | ✅    |
| `LinkPopover.tsx`        | 辅助 | 链接 hover 预览卡片（标题/摘要/favicon/siteName/authority badge/相对时间/Agent浏览入口）               | ✅    |
| `MarkdownImage.tsx`      | 核心 | Markdown 图片：lazy load、Lightbox、尺寸约束                                                           | ✅    |
| `MathRenderer.tsx`       | 核心 | KaTeX 行内/块级公式渲染                                                                                | ✅    |
| `MermaidChart.tsx`       | 核心 | Mermaid 图表交互式渲染（lazy渲染、错误降级、pinch/wheel/button缩放、拖拽平移、全屏、图例过滤）         | ✅    |
| `MermaidLegendPanel.tsx` | 辅助 | Mermaid 图例/节点说明侧栏                                                                              | ✅    |
| `ThinkBox.tsx`           | 核心 | 模型思考链折叠展示容器                                                                                 | ✅    |
| `ThinkTagProcessor.tsx`  | 辅助 | `` 标签预处理与分段                                                                                    | ✅    |
| `mermaid-theme.ts`       | 辅助 | Mermaid 明暗主题 token 映射                                                                            | ✅    |
| `ResponsiveTable.tsx`    | 核心 | Markdown 表格响应式渲染：overflow-x-auto 防溢出、移动端多列卡片视图、Toggle 切换、colspan/rowspan 容错 | ✅    |
| `rehypeHeadingIds.ts`    | 辅助 | rehype 插件：为 heading 注入 anchor id                                                                 | ✅    |
| `__tests__/LinkPopover.test.tsx` | 测试 | 链接 hover 预览卡片、相对时间格式化与 anchor/span 状态单测                                            | ✅    |

## 依赖

- `@/lib/diff/DiffViewer`（共享 Diff 可视化组件，InlineDiffViewer 为薄包装层）
- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
