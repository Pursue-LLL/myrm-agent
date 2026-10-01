# lib/utils/

通用纯函数工具集（认证头、导出、剪贴板、Agent 映射等）。**无** React 组件。

按域单文件组织；新工具优先就近放 feature/lib 子目录，仅跨 3+ feature 复用才放此处。

子目录 `__tests__/` 覆盖高价值纯函数。

- `localeUtils.ts`：Locale 工具集 — cookie 常量、客户端读取、后端格式映射、营销参数解析、RFC 7231 Accept-Language 协商。
- `responseLocalePolicy.ts`：Agent `engine_params.response_locale_policy` 读写（正式韩语 Switch ↔ harness suffix SSOT）。
- `mcpConfigNormalizer.ts`：MCP transport/keepalive 语义归一化（`http` → `streamable_http`；`stdio` keepalive 清空）。
- `subagentTree.ts`：Subagent 树数据工具 — 构建树、子树聚合（成本/tokens/后代）、全局统计、排序（spawn/busiest/slowest/status）、过滤（all/running/failed/leaf）、展平、格式化（fmtCost/fmtTokens/fmtBudgetCost）、预算/用量提取（extractCostUsd/extractTotalTokens/extractBudgetTokens/extractMaxCostUsd，成本经 `token_usage.total_cost_usd`，上限经 `budget.max_cost_usd`/`budget.budget_tokens`）。
- `taskTopologyModel.ts`：任务拓扑数据模型 — 纯函数把 subagent 树 / fission 拓扑转为 ReactFlow 可渲染图模型（buildTopologyModel / buildFissionTopologyModel / buildMergedTopologyModel：节点/边/墓碑/焦点/进度/元数据、悬空边过滤、label 截断、状态 tone 映射；**验证失败节点 tone 降级为 danger 并透传 verification 字段**；fission 命名空间按 fission_id 隔离）。
- `fileUtils.ts`：通用文件工具 — 扩展名分类（image/video/audio/pdf/document/text）、MIME 推断（getMimeType）、扩展名提取（getFileExtension）、文件名非法字符清理（sanitizeFilename）、Web/Tauri 展示 URL（getDisplayUrl）、base64 转换（fetchFileAsBase64DataURL）、SHA-256 哈希（computeFileHash）、「路径→内容」DEFLATE zip 打包（buildZipFromFiles）、文件下载（triggerDownload：Web a[download] / Tauri 系统保存对话框 + fs 写入）。
- `imeUtils.ts`：输入法组合输入守卫 — `isImeComposing` 统一判断 `nativeEvent.isComposing`、`event.isComposing`、`key === 'Process'` 与 `keyCode === 229`；另用 document 级 `compositionend` 观察器维护 `IME_CONFIRM_ENTER_WINDOW_MS`（100ms）时间窗，补偿 Safari / WebKit（含 Tauri macOS WebView）「先派发 compositionend、再派发确认 keydown 且 isComposing 已为 false、keyCode 已为 13」的顺序倒置，保障 Windows/macOS/iOS/Android 输入法候选词确认不误触发消息提交。
- `titleUtils.ts`：会话标题消歧与序号自增 — `parseTitleIndex` 与 `disambiguateChatTitle` 纯函数，确保自动生成和重命名标题时保持全局列表唯一可辨（如自动追加 `(2)`、`(3)`）。
- `pathValidation.ts`：全平台路径规范、工作区校验与展示截断 — 支持 POSIX、Windows 盘符、Windows UNC 共享路径识别与反斜杠/正斜杠归一化，提供 `validateWorkspacePath` 进行 ~ 波浪号路径解析与非法控制字符防护，以及 `formatPathForDisplay` 智能居中省略截断。
- `skillUtils.ts`：Skill 多语言描述容灾守卫 — `resolveSkillDescription` 统一去除空串与空白，并在缺失时回退默认国际化文案，杜绝卡片与详情页空白。
- `typeUtils.ts`：安全字典与类型守卫 — `isRecord`、`asRecord` 与 `safeGet`，彻底防止服务端 dict-like 异常或嵌套层级缺失导致的 WebUI 运行时白屏与崩溃。
- `errorRedactor.ts`：Control UI 全面错误展示脱敏引擎 — `redactErrorMessage` 与 `redactErrorObject` 纯函数，覆盖 API Key、Bearer Token、JWT、数据库 URI 密码、macOS/Linux/Windows 主目录路径与私有内网 IP 地址，保障 UI 表面（Toast、API 响应解析、内联错误文本）零凭据泄漏。
- `encodingUtils.ts`：UTF-8 安全 Base64 编解码引擎 — `safeBase64DecodeUtf8` 与 `safeBase64EncodeUtf8` 纯函数，基于原生 `TextDecoder('utf-8')` / `TextEncoder` 还原多字节 Unicode 字节流，杜绝原生 `atob` 导致的中文、日韩文与 Emoji 数据乱码崩溃，具备优雅容错降级保护。
- `urlUtils.ts`：URL 协议安全性与外部跳转校验工具 — 提供 `isValidExternalUrl` 严格协议白名单校验（仅放行 `http:` 与 `https:`），阻断 `javascript:`、`data:` 与桌面本地伪协议，防御工件与应用外链 XSS 及客户端沙箱逃逸。
- `imageAdmission.ts`：端侧图片准入与轻量速压防线 — `admitAndCompressImageFile` 与 `admitAndCompressFiles` 纯函数，入队/上传前执行尺寸（<=2048px）与体积（<=4MB）预检，基于 `OffscreenCanvas` / `createImageBitmap` 异步等比缩放与无损感知 WebP 压缩，杜绝超大原图（30MB+）阻塞网络带宽与网关 413 崩溃，保全动图（GIF）与矢量图（SVG）。
- `chatExport.ts`：会话多格式导出排版与文件构建纯函数 — 支持 Markdown / JSON 结构化格式化、工业级敏感凭据安全脱敏正则过滤、细粒度思考链/工具细节包含控制、单条消息导出 CWE-312 脱敏保护（含图片导出离屏 DOM 克隆安全清洗）、客户端自适应下载触发。
- `chatExportHtml.ts`：会话离线独立 HTML 渲染构建器 — 基于 Rehype AST 引擎生成安全 HTML，集成代码高亮、iframe 挂件与自包含代码块一键复制交互按钮，保证 100% 零原生 Emoji 并自包含渲染。
- `chatExportHtmlTemplates.ts`：会话 HTML 导出组件与样式模板库 — 封装深浅双主题 CSS 变量、Highlight.js 语法主题、离线响应式自适应布局、打印态样式隔离防截断、原生代码复制交互脚本与反馈动画、主题切换交互脚本与多语言元数据统计标签。
- `clientRedact.ts`：客户端轻量敏感凭据脱敏清洗工具 — 提供 `redactSensitiveClientText` 与 `containsSensitiveData` 纯函数，覆盖 OpenAI/Anthropic 风格 API Keys、GitHub Tokens、AWS 密钥、PEM 私钥、JWT 签名凭据与键值对密码，防御单条消息与前端导出 CWE-312 敏感信息明文泄露。
