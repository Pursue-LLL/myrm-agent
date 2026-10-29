# lib/utils/chat-export/

会话导出域子包：多格式导出排版、批量 zip 编排、离线 HTML 渲染与样式模板。**无** React 组件，全部纯函数与构建器。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/chat-export`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖导出排版、HTML 构建与批量编排行为，另有三组专项：`exportUrlPolicy.test.ts` 逐个钉住放行与拒绝的链接目标，`chatExportHtmlHostile.test.ts` 用恶意 Markdown 与恶意来源链接验证导出文件里没有能执行脚本的链接，`chatExportHtmlContrast.test.ts` 从样式表解析出两套主题的颜色并校验每一组文字与底色的对比度 ≥ 4.5。

- `index.ts`：域门面 barrel — 显式导出清单聚合 `chatExport.ts` 与 `batchExport.ts` 公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `chatExport.ts`：导出数据模型与多格式排版 — ExportMessage/ExportChat/ExportData 类型、Markdown/JSON 格式化、敏感凭据脱敏过滤、思考链/工具细节包含控制、单条消息导出（Markdown/Docx/Html/Image，CWE-312 脱敏防护）、剪贴板写入、打印与客户端自适应下载触发；HTML 文档构建经惰性动态 import 调用 `chatExportHtml.ts`。
- `batchExport.ts`：批量导出编排器 — 3 并发 + 1 次重试调用 `services/chat::exportChat`，markdown/json/html 三格式内容构建（html 走惰性动态 import `chatExportHtml.ts`），按日期归档目录与重名消歧，DEFLATE zip 打包，进度/取消回调。
- `chatExportHtml.ts`：Markdown-to-HTML 导出渲染器 — Rehype AST 安全渲染（默认全转义 + 细粒度放行）、代码高亮、iframe 挂件、自包含代码块一键复制交互，导出文档 100% 零原生 Emoji 自包含渲染；管线最后一步 `rehypeSafeLinks` 与来源列表都经 `exportUrlPolicy.ts` 判定链接目标。
- `exportUrlPolicy.ts`：导出文件里的链接目标策略 — `isSafeLinkUrl` 只放行 `http` / `https` / `mailto` / `tel` 与无协议的相对地址（用浏览器同一套 URL 解析判定，tab、换行与前导控制字符的写法也不例外），`rehypeSafeLinks` 把被拒绝的链接变成不带 `href` 的纯文字，文字保留；导出文件在应用之外打开，能执行脚本的链接不能进入文件；包内私有。
- `chatExportHtmlTemplates.ts`：导出 HTML 组件与样式模板库 — 深浅双主题 CSS 变量（文字颜色一律取自变量，含成功色 `--ok`、失败色 `--danger`、徽标字色 `--on-accent`，两套主题下每组文字与底色的对比度 ≥ 4.5）、Highlight.js 语法主题、离线响应式自适应布局、打印态样式隔离与暗黑模式白底强制反转、复制/主题切换交互脚本、多语言元数据统计标签；包内私有，外部消费经 `chatExportHtml.ts` 间接触达。

## 依赖

- `@/lib/utils/fileUtils`（POS: 通用文件工具）— 文件名清理与下载触发。
- `@/lib/utils/error-handling`（POS: 客户端轻量敏感凭据脱敏清洗工具）— 导出内容脱敏。
- `@/lib/utils/clipboardUtils`（POS: 剪贴板工具）— Markdown 复制写入。
- `@/services/chat`（POS: 聊天 API 请求层）— 单聊天导出数据源（`batchExport.ts` 批量编排消费）。
