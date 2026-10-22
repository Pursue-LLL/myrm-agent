# artifacts/renderers/

按 MIME/类型分发的工件预览渲染器注册表消费方。

| 文件                                   | 职责                                                                                                                                                                                                        |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CodePreview.tsx`                      | 代码/Sandpack                                                                                                                                                                                               |
| `DocumentPreview.tsx`                  | Markdown/HTML 文档                                                                                                                                                                                          |
| `MediaPreview.tsx`                     | `HtmlPreview` 沙箱 iframe（`widget-navigate` 外链经 `lib/untrusted-link.ts`：仅放行 http(s)，桌面端须用户确认）、图片/视频/音频预览；`SvgPreview` 按 `LARGE_FILE_THRESHOLD` 分流：常规体积 DOMPurify 内联，超限走 Blob URL + `<img>` 原生栅格化     |
| `MermaidPreview.tsx`                   | Mermaid 图                                                                                                                                                                                                  |
| `McpAppViewer.tsx`                     | MCP App iframe：私有 postMessage 方言（未实现 ext-apps 的 `ui/*` JSON-RPC 桥）；`openLink` / `widget-navigate` 外链经 `lib/untrusted-link.ts`：仅放行 http(s)，桌面端须用户确认，来源名取 `view.serverName` |
| `SpreadsheetPreview/`                  | CSV/XLSX 表格只读预览                                                                                                                                                                                       |
| `SpreadsheetEditor/`                   | XLSX Live 编辑器（Univer Sheet + SheetJS 双向转换）                                                                                                                                                         |
| `DocxPreview/`                         | Word 文档（docx-preview 库）                                                                                                                                                                                |
| `PptxPreview/`                         | 演示文稿（@aiden0z/pptx-renderer 库）                                                                                                                                                                       |
| `architecture/`                        | 交互式架构图/拓扑图（@xyflow/react + @dagrejs/dagre 引擎，含演化 Diff、BFS 最短路径探查、SVG/JSON 导出）                                                                                                    |
| `DiffPreview.tsx`                      | 版本间差异对比（Monaco DiffEditor，inline/side-by-side）                                                                                                                                                    |
| `NoPreview.tsx` / `SkeletonLoader.tsx` | 占位与加载                                                                                                                                                                                                  |

## 测试

| 文件                              | 职责                                                                                                                                                                    |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `__tests__/MediaPreview.test.tsx` | `HtmlPreview` 的 `widget-navigate` 中继：只接受自身 iframe 的消息，仅放行 http(s) 外链；桌面端不直接打开而交给确认弹窗，爆发请求只保留一条                              |
| `__tests__/SvgPreview.test.tsx`   | `SvgPreview` 阈值分流：小文件 DOMPurify 内联并清洗脚本；大文件 Blob URL + `<img>` 栅格化，URL 在内容变化 / 卸载时回收，加载失败降级为错误提示                          |
| `__tests__/McpAppViewer.test.tsx` | `McpAppViewer` 的 `openLink` / `app:openLink` / `widget-navigate` 中继：浏览器直接开新标签页，桌面端交给确认弹窗并带上服务器名，非 http(s) 与非自身 iframe 的请求被丢弃 |
| `__tests__/DiffPreview.test.tsx`  | `DiffPreview` 版本不足的占位、inline / side-by-side 切换、版本标签与原文 / 修改文的取值                                                                                 |
