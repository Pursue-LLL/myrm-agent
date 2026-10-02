# lib/utils/chat-export/

会话导出域子包：多格式导出排版、离线 HTML 渲染与样式模板。**无** React 组件，全部纯函数与构建器。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/chat-export`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖导出排版与 HTML 构建行为。

- `index.ts`：域门面 barrel — `export *` 聚合 `chatExport.ts` 公开符号，组件层统一导入入口。
- `chatExport.ts`：导出数据模型与多格式排版 — ExportMessage/ExportChat/ExportData 类型、Markdown/JSON 格式化、敏感凭据脱敏过滤、思考链/工具细节包含控制、单条消息导出（Markdown/Docx/Html/Image，CWE-312 脱敏防护）、剪贴板写入、打印与客户端自适应下载触发；HTML 文档构建经惰性动态 import 调用 `chatExportHtml.ts`。
- `chatExportHtml.ts`：Markdown-to-HTML 导出渲染器 — Rehype AST 安全渲染（默认全转义 + 细粒度放行）、代码高亮、iframe 挂件、自包含代码块一键复制交互，导出文档 100% 零原生 Emoji 自包含渲染。
- `chatExportHtmlTemplates.ts`：导出 HTML 组件与样式模板库 — 深浅双主题 CSS 变量、Highlight.js 语法主题、离线响应式自适应布局、打印态样式隔离与暗黑模式白底强制反转、复制/主题切换交互脚本、多语言元数据统计标签；包内私有，外部消费经 `chatExportHtml.ts` 间接触达。

## 依赖

- `@/lib/utils/fileUtils`（POS: 通用文件工具）— 文件名清理与下载触发。
- `@/lib/utils/clientRedact`（POS: 客户端轻量敏感凭据脱敏清洗工具）— 导出内容脱敏。
- `@/lib/utils/clipboardUtils`（POS: 剪贴板工具）— Markdown 复制写入。
- 同域编排层 `@/lib/utils/batchExport.ts` 深路径引用 `chatExportHtml.ts::buildHtmlDocument`（批量 zip 流水线内构 HTML 文档）；域内协作直达内部构件，不绕 barrel 门面。
