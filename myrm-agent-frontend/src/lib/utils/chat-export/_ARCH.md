# lib/utils/chat-export/

会话导出域子包：多格式导出排版、批量 zip 编排、离线 HTML 渲染与样式模板。**无** React 组件，全部纯函数与构建器。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/chat-export`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖导出排版、HTML 构建与批量编排行为，另有十二组专项：`exportUrlPolicy.test.ts` 逐个钉住放行与拒绝的链接目标，`chatExportHtmlHostile.test.ts` 用恶意 Markdown 与恶意来源链接验证导出文件里没有能执行脚本的链接，`chatExportHtmlContrast.test.ts` 从样式表解析出两套主题的颜色并校验每一组文字与底色的对比度 ≥ 4.5，`chatExportHtmlMath.test.ts` 验证价格句不被配成公式、三种写法都渲染成公式、代码里的 `$` 与 `%` 原样、`\href` / `\includegraphics` 不产生链接或图片，`katexExportStyle.test.ts` 用安装的 KaTeX 样式表与字体验证内联结果（字体嵌入且逐字节一致、取不到的字体被丢弃、只缓存完整结果、并发共享一次抓取），`chatExportHtmlKatexStyle.test.ts` 钉住只有含公式的导出才带 KaTeX 样式，`printHtmlDocument.test.ts` 验证打印等字体就绪、等待有上限且 iframe 事后移除，`printChat.test.ts` 钉住打印的是按所选主题与语言构建的文档，`chatExportHtmlStatic.test.ts` 钉住静态版本没有脚本、主题按钮与复制按钮、公式只留一份 TeX 文本、不取 KaTeX 样式，`chatExportHtmlEngine.test.ts` 钉住两种模式各建一次 Markdown 引擎、构建失败后下次重试且不牵连另一种模式，`chatExportDocxContent.test.ts` 用真实的 `docshift` 转换静态版本并读回 DOCX 文本（没有页面控件与脚本文字、每个公式一次），`downloadMessageAsDocx.test.ts` 钉住 DOCX 转换的是静态版本。

- `index.ts`：域门面 barrel — 显式导出清单聚合 `chatExport.ts` 与 `batchExport.ts` 公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `chatExport.ts`：导出数据模型与多格式排版 — ExportMessage/ExportChat/ExportData 类型、Markdown/JSON 格式化、敏感凭据脱敏过滤、思考链/工具细节包含控制、单条消息导出（Markdown/Docx/Html/Image，CWE-312 脱敏防护；Docx 转换的是 `chatExportHtml.ts` 的静态版本）、剪贴板写入、打印（经 `printHtmlDocument.ts`）与客户端自适应下载触发；HTML 文档构建经惰性动态 import 调用 `chatExportHtml.ts`。
- `batchExport.ts`：批量导出编排器 — 3 并发 + 1 次重试调用 `services/chat::exportChat`，markdown/json/html 三格式内容构建（html 走惰性动态 import `chatExportHtml.ts`），按日期归档目录与重名消歧，DEFLATE zip 打包，进度/取消回调。
- `chatExportHtml.ts`：Markdown-to-HTML 导出渲染器 — Rehype AST 安全渲染（默认全转义 + 细粒度放行）、代码高亮、iframe 挂件、自包含代码块一键复制交互，导出文档 100% 零原生 Emoji 自包含渲染；管线最后一步 `rehypeSafeLinks` 与来源列表都经 `exportUrlPolicy.ts` 判定链接目标；公式经 `../markdownMath` 渲染（`mathPlugins`，KaTeX 保持默认值），含公式的导出另由 `katexExportStyle.ts` 内联 KaTeX 样式表与字体（没有公式的导出不付这份体积）；`HtmlDocumentOptions.static` 出静态版本供 DOCX 转换器读：没有主题按钮、复制按钮与脚本（转换器会把它们当文字写进 Word），公式经 `texSourceMathPlugins` 留作 TeX 源码（行内 `$…$`、块级 `$$…$$`，转换器不会把 KaTeX 的 MathML 与 HTML 两半都写出来，也就不需要 KaTeX 样式）；两种模式各缓存一个 Markdown 引擎，构建失败不缓存、下次重试。`docshift` 把每个最外层 `div` 读成一个段落，所以消息正文（包在 `.message` 与 `.msg-body` 里）的列表不会进入 DOCX，标题与表格降为普通段落。
- `katexExportStyle.ts`：导出文件里的 KaTeX 样式 — 自己 `import 'katex/dist/katex.min.css'`（样式表随这个懒加载块一起装载，在没有聊天内容的页面上导出也取得到），运行时从 `document.styleSheets` 取 `.katex` 规则与 `KaTeX_*` 的 `@font-face`，把 woff2 抓成 data URI 内联，导出文件离线打开也能排版公式；取不到的字体被丢弃（回退系统字体）而不是让导出失败，只缓存完整结果，并发导出共享一次抓取；没有 `document` 或没有可读的 KaTeX 样式表时返回空串；包内私有。
- `printHtmlDocument.ts`：打印导出文档 — 隐藏 iframe 写入文档，等 `load`（上限 1.5 s）与 `document.fonts.ready`（上限 3 s；内嵌字体的解码晚于 `load`）之后调起 `print()`，iframe 3 s 后移除；包内私有，由 `chatExport.ts::printChat` 调用。
- `exportUrlPolicy.ts`：导出文件里的链接目标策略 — `isSafeLinkUrl` 只放行 `http` / `https` / `mailto` / `tel` 与无协议的相对地址（用浏览器同一套 URL 解析判定，tab、换行与前导控制字符的写法也不例外），`rehypeSafeLinks` 把被拒绝的链接变成不带 `href` 的纯文字，文字保留；导出文件在应用之外打开，能执行脚本的链接不能进入文件；包内私有。
- `chatExportHtmlTemplates.ts`：导出 HTML 组件与样式模板库 — 深浅双主题 CSS 变量（文字颜色一律取自变量，含成功色 `--ok`、失败色 `--danger`、徽标字色 `--on-accent`，两套主题下每组文字与底色的对比度 ≥ 4.5）、Highlight.js 语法主题、离线响应式自适应布局、打印态样式隔离与暗黑模式白底强制反转、复制/主题切换交互脚本、多语言元数据统计标签；包内私有，外部消费经 `chatExportHtml.ts` 间接触达。

## 依赖

- `@/lib/utils/fileUtils`（POS: 通用文件工具）— 文件名清理与下载触发。
- `@/lib/utils/error-handling`（POS: 客户端轻量敏感凭据脱敏清洗工具）— 导出内容脱敏。
- `@/lib/utils/clipboardUtils`（POS: 剪贴板工具）— Markdown 复制写入。
- `@/services/chat`（POS: 聊天 API 请求层）— 单聊天导出数据源（`batchExport.ts` 批量编排消费）。
