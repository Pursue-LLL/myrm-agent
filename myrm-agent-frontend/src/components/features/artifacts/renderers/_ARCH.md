# artifacts/renderers/

按 MIME/类型分发的工件预览渲染器注册表消费方。

| 文件                                   | 职责                                                                                                     |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `CodePreview.tsx`                      | 代码/Sandpack                                                                                            |
| `DocumentPreview.tsx`                  | Markdown/HTML 文档                                                                                       |
| `MediaPreview.tsx`                     | 图片/音视频                                                                                              |
| `MermaidPreview.tsx`                   | Mermaid 图                                                                                               |
| `McpAppViewer.tsx`                     | MCP App iframe                                                                                           |
| `SpreadsheetPreview/`                  | CSV/XLSX 表格只读预览                                                                                    |
| `SpreadsheetEditor/`                   | XLSX Live 编辑器（Univer Sheet + SheetJS 双向转换）                                                      |
| `DocxPreview/`                         | Word 文档（docx-preview 库）                                                                             |
| `PptxPreview/`                         | 演示文稿（@aiden0z/pptx-renderer 库）                                                                    |
| `architecture/`                        | 交互式架构图/拓扑图（@xyflow/react + @dagrejs/dagre 引擎，含演化 Diff、BFS 最短路径探查、SVG/JSON 导出） |
| `DiffPreview.tsx`                      | 版本间差异对比（Monaco DiffEditor，inline/side-by-side）                                                 |
| `NoPreview.tsx` / `SkeletonLoader.tsx` | 占位与加载                                                                                               |
