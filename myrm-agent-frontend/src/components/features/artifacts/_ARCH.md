# artifacts/ 模块架构

---

## 架构概述

聊天流工件展示：Globe 多 target 发布、preflight 门禁、只读分享短链、知识库写入、对话附件插入。视觉型工件（HTML/SVG/Mermaid）默认在消息流内 inline 展开渲染，其余类型保持卡片模式。卡片与全屏预览双入口一致。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `ArtifactCard.tsx` | 核心 | 聊天卡片；HTML/SVG/Mermaid 默认 inline 渲染；Globe 发布；publication badges；per-target stale banner |
| `PublishModal.tsx` | 核心 | 多 target 发布；target 下拉 + `/publish` + WS + Settings 深链 |
| `artifactUtils.ts` | 辅助 | preflight/share API、`isPublicationStale`、`publicationsChanged` |
| `ArtifactRenderer.tsx` | 核心 | 多类型工件渲染路由 |
| `ReactPreview.tsx` | 核心 | React 组件纯预览器（Sandpack）；视图切换由 PortalHeader 统一控制 |
| `components/SandpackErrorBoundary.tsx` | 辅助 | Sandpack 编译/运行时错误边界 |
| `components/CompileErrorDisplay.tsx` | 辅助 | Sandpack 编译错误展示面板 |
| `renderers/MediaPreview.tsx` | 辅助 | `HtmlPreview` 沙箱 iframe; `SvgPreview` DOMPurify 安全渲染 |
| `renderers/MermaidPreview.tsx` | 辅助 | Mermaid 图表渲染（Suspense + dynamic import） |
| `portal/useSelectionAction.ts` | 辅助 | Artifact 选中交互的通用消息发送 hook（dirtyArtifacts 注入 + Agent 忙碌排队） |
| `portal/SelectionToolbar.tsx` | 辅助 | Monaco Editor 选中文本悬浮操作栏 |
| `portal/DocumentSelectionToolbar.tsx` | 辅助 | 文档预览 DOM 选中文本悬浮操作栏 |
| `portal/ElementPickerToolbar.tsx` | 辅助 | DOM 元素拾取指令栏 |
| `renderers/DocumentPreview.tsx` | 核心 | 文档/Markdown 渲染预览（集成 DocumentSelectionToolbar） |
| `renderers/SpreadsheetPreview/` | 辅助 | CSV/TSV/XLSX 表格预览 |

---

## 依赖关系

- `@/services/hosting.ts`：targets CRUD、publish、publications、WS URL
- `@/lib/api`：artifact GET
- `@/store/chat`：`publications[]` 同步
- `app/api/files/hosting_api.py`、`artifact_share_api.py`（服务端）
