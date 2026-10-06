# lib/utils/

通用纯函数工具集（认证头、导出、剪贴板、Agent 映射等）。**无** React 组件。

按域组织（平铺单文件或域子包）；新工具优先就近放 feature/lib 子目录，仅跨 3+ feature 复用才放此处；同域多文件必须收敛为域子包（barrel 门面 + `_ARCH.md`）。

子目录 `__tests__/` 覆盖高价值纯函数。

- `relativeTime.ts`：Locale 感知相对时间格式化 — `formatRelativeTime` 基于 `Intl.RelativeTimeFormat`（auto 措辞，六语言原生支持），秒/分/时/日/月/年自适应档位与 NaN 容错空串降级；模块级 formatter 缓存（locale → `Intl.RelativeTimeFormat`），高频轮询场景免重复构造。
- `responseLocalePolicy.ts`：Agent `engine_params.response_locale_policy` 读写（正式韩语 Switch ↔ harness suffix SSOT）。
- `fileUtils.ts`：通用文件工具 — 扩展名分类（image/video/audio/pdf/document/text）、MIME 推断（getMimeType）、扩展名提取（getFileExtension）、文件名非法字符清理（sanitizeFilename）、Web/Tauri 展示 URL（getDisplayUrl）、base64 转换（fetchFileAsBase64DataURL）、SHA-256 哈希（computeFileHash）、「路径→内容」DEFLATE zip 打包（buildZipFromFiles）、文件下载（triggerDownload：Web a[download] / Tauri 系统保存对话框 + fs 写入）。
- `imeUtils.ts`：输入法组合输入守卫 — `isImeComposing` 统一判断 `nativeEvent.isComposing`、`event.isComposing`、`key === 'Process'` 与 `keyCode === 229`；另用 document 级 `compositionend` 观察器维护 `IME_CONFIRM_ENTER_WINDOW_MS`（100ms）时间窗，补偿 Safari / WebKit（含 Tauri macOS WebView）「先派发 compositionend、再派发确认 keydown 且 isComposing 已为 false、keyCode 已为 13」的顺序倒置，保障 Windows/macOS/iOS/Android 输入法候选词确认不误触发消息提交。
- `titleUtils.ts`：会话标题消歧与序号自增 — `parseTitleIndex` 与 `disambiguateChatTitle` 纯函数，确保自动生成和重命名标题时保持全局列表唯一可辨（如自动追加 `(2)`、`(3)`）。
- `timeUtils.ts`：挂钟时间工具 — `formatDuration` 紧凑运行时长（42s/8m 30s，对齐后端 `_format_duration`）、`getCurrentTimestamp` unix 秒、`formatMessageTimestamp` 消息时间戳（label 行内四档：今日/昨日/同年/跨年，`Intl.DateTimeFormat` 六语言原生 + hourCycle h23（24 小时制）；title hover 完整时间走 locale 原生小时制（en 12h / zh 24h）；模块级 formatter 缓存，实测 18.7 倍于逐次 toLocaleString）。
- `pathValidation.ts`：全平台路径规范、工作区校验与展示截断 — 支持 POSIX、Windows 盘符、Windows UNC 共享路径识别与反斜杠/正斜杠归一化，提供 `validateWorkspacePath` 进行 ~ 波浪号路径解析与非法控制字符防护，以及 `formatPathForDisplay` 智能居中省略截断。
- `skillUtils.ts`：Skill 多语言描述容灾守卫 — `resolveSkillDescription` 统一去除空串与空白，并在缺失时回退默认国际化文案，杜绝卡片与详情页空白。
- `typeUtils.ts`：安全字典与类型守卫 — `isRecord`、`asRecord` 与 `safeGet`，彻底防止服务端 dict-like 异常或嵌套层级缺失导致的 WebUI 运行时白屏与崩溃。
- `encodingUtils.ts`：UTF-8 安全 Base64 编解码引擎 — `safeBase64DecodeUtf8` 与 `safeBase64EncodeUtf8` 纯函数，基于原生 `TextDecoder('utf-8')` / `TextEncoder` 还原多字节 Unicode 字节流，杜绝原生 `atob` 导致的中文、日韩文与 Emoji 数据乱码崩溃，具备优雅容错降级保护。
- `urlUtils.ts`：URL 协议安全性与外部跳转校验工具 — 提供 `isValidExternalUrl` 严格协议白名单校验（仅放行 `http:` 与 `https:`），阻断 `javascript:`、`data:` 与桌面本地伪协议，防御工件与应用外链 XSS 及客户端沙箱逃逸。
- `imageAdmission.ts`：端侧图片准入与轻量速压防线 — `admitAndCompressImageFile` 与 `admitAndCompressFiles` 纯函数，入队/上传前执行尺寸（<=2048px）与体积（<=4MB）预检，基于 `OffscreenCanvas` / `createImageBitmap` 异步等比缩放与无损感知 WebP 压缩，杜绝超大原图（30MB+）阻塞网络带宽与网关 413 崩溃，保全动图（GIF）与矢量图（SVG）。
- `chat-export/`：会话导出域子包 — `index.ts` 显式清单门面（对外唯一入口 `@/lib/utils/chat-export`，公开面受控）；`chatExport.ts` 多格式导出排版与文件构建纯函数（Markdown / JSON 结构化格式化、敏感凭据脱敏过滤、单条消息 CWE-312 保护、客户端自适应下载）；`batchExport.ts` 批量导出编排器（3 并发 + 重试、日期归档、DEFLATE zip、进度/取消回调）；`chatExportHtml.ts` 离线独立 HTML 渲染构建器（Rehype AST 安全 HTML、代码高亮、iframe 挂件、零原生 Emoji 自包含渲染，惰性动态加载）；`chatExportHtmlTemplates.ts` 深浅双主题样式模板库（主题 CSS 变量、Highlight.js 语法主题、打印态隔离、复制交互脚本、多语言统计标签，包内私有）。详见 [chat-export/_ARCH.md](chat-export/_ARCH.md)。
- `error-handling/`：错误处理域子包 — 展示脱敏引擎（errorRedactor：API Key/Bearer/JWT/URI 密码/主目录/内网 IP 全覆盖）、客户端轻量脱敏清洗（clientRedact：CWE-312 防护）、技能错误映射（skillErrorMapper：技术错误→翻译键）与错误去重管理器（errorManager：30 秒窗口），barrel 门面 `@/lib/utils/error-handling`。详见 [error-handling/_ARCH.md](error-handling/_ARCH.md)。
- `mcp-config/`：MCP 配置域子包 — transport/keepalive 语义归一化（Normalizer）、JSON 配置解析（Parser）与扫描 finding 文案（ScanFindingText），barrel 门面 `@/lib/utils/mcp-config`。详见 [mcp-config/_ARCH.md](mcp-config/_ARCH.md)。
- `agent-config/`：Agent 配置域子包 — Agent → AgentConfig 映射构建（Mapper）与依赖缺失校验（Validator），barrel 门面 `@/lib/utils/agent-config`。详见 [agent-config/_ARCH.md](agent-config/_ARCH.md)。
- `device/`：设备检测域子包 — 环境侧移动端判定（deviceDetection）与特征查询级设备判定（deviceUtils），零外部依赖，barrel 门面 `@/lib/utils/device`。详见 [device/_ARCH.md](device/_ARCH.md)。
- `media/`：媒体凭据域子包 — 图片/TTS/视频三通道凭据就绪判定与警告收集（CredentialReadiness）、provider 状态映射与后端状态拉取（ProviderStatus），barrel 门面 `@/lib/utils/media`。详见 [media/_ARCH.md](media/_ARCH.md)。
- `locale/`：Locale 域子包 — cookie 常量、客户端读取、后端格式映射、营销参数解析、RFC 7231 Accept-Language 协商（localeUtils）与多语言文本选择（localeText），barrel 门面 `@/lib/utils/locale`。详见 [locale/_ARCH.md](locale/_ARCH.md)。
- `subagent/`：Subagent 数据域子包 — subagent 树数据工具（subagentTree）、任务拓扑图模型（taskTopologyModel）与阶段任务计数推导（stageTaskCount），barrel 门面 `@/lib/utils/subagent`。详见 [subagent/_ARCH.md](subagent/_ARCH.md)。
- `a11y.ts`：键盘可达性 — `activateOnKey` 为 `role="button"` / `role="link"` + `tabIndex={0}` 的非原生交互元素（div/span）提供键盘激活（按钮：Enter / 空格；链接：仅 Enter，空格留给页面滚动），触发元素自身原生 click 以复用既有 `onClick`（键盘与鼠标同源）；子元素冒泡的按键与带修饰键的组合键不劫持。
- `apiConfig.ts`：后端服务基础 URL 访问 — `getBackendUrl` 统一后端基础地址出口（不含 API 路径前缀）。
- `backend-url.ts`：后端服务基础地址层 — `BACKEND_BASE_URL` 动态解析常量与 `createDynamicUrl` 动态 URL 构建器（懒解析 toString/valueOf 伪装 string），独立于 API 请求层供 URL 类工具与 API 层共同消费。
- `authHeaders.ts`：认证请求头构建 — 认证 token 读取（localStorage `auth_token`）与 `getAuthHeaders` 请求头组装，SSR 安全（window 未定义返回空）。
- `avatarUtils.ts`：智能体头像解析工具层 — `parseAvatarUrl` 统一解析 avatar URL（icon:/lucide:/emoji:/home:///http(s):///gradient: 六格式）与 `isIconAvatar` 快捷判断、`ParsedAvatar` 结果类型。
- `classnameUtils.ts`：类名合并 — `cn` 组合 clsx 条件拼接与 tailwind-merge 冲突消解。
- `clipboardUtils.ts`：Tauri/Web 双环境剪贴板封装 — `isTauri` 运行环境检测与 `writeToClipboard` 双路径写入（Tauri 插件 / Web API）。
- `completionSound.ts`：完成提示音 — Web Audio API 双音符柔和提示（G4→C5 纯四度），零外部音频文件依赖，仅在用户非注视页面时播放。
- `componentPreloader.ts`：重型组件预加载 — hover 触发 Monaco/Sandpack 提前加载，优化首次渲染体验。
- `cronEstimate.ts`：定时表达式估算 — cron/interval/once 三类调度月执行次数估算。
- `diagnostic-export.ts`：诊断导出 — `formatDoctorReportAsMarkdown` GitHub Issue 友好格式化、`buildDiagnosticBundle` 诊断 JSON 组装（含客户端上下文）、复制与下载触发。
- `domUtils.ts`：DOM 滚动检测 — `isNearBottom` 滚动接近底部判定（阈值可调）。
- `hardwareSimulator.ts`：硬件阶梯估算 — HardwareRungInfo 阶梯信息与 64k 上下文 KV Cache 内存估算。
- `messageUtils.ts`：消息处理工具 — 时间戳标签剥离、ui_action JSON 块剥离、用户消息展示清理、explicit skill wire（`[use s1,s2]`）解析与构建、skill chip 展示名、markdown 纯化、浏览器时区获取。
- `modelFormatUtils.ts`：数值紧凑格式化 — token 数量 K/M 紧凑展示。
- `networkResilience.ts`：网络韧性策略层 — HTTP 状态码瞬时错误可重试判定、WebSocket close code 可重试判定、`FatalNetworkError` 不可重试错误类、归档恢复校验失效识别，统一重试与 fail-fast 决策。
- `reactCodeProcessor.ts`：React 代码检测 — `isValidReactCode` 有效性判定（React import/JSX/export 三要素）与工件预览依赖处理。
- `reactUtils.ts`：React children 工具 — `getChildrenAsText` children prop 纯文本转换。
- `requestManager.ts`：全局请求管理 — 流式 AI 搜索请求注册、跟踪与取消（AbortController 集合管理）。
- `teammateMessage.ts`：teammate 消息归一 — `normalizeTeammateEntry` 消息行（message_id/from/to/body/created_at）到 `TeammateMessageEntry` 归一。
- `toast.ts`：Toast 统一包装 — 兼容 shadcn/ui 与 Sonner 双 API 形态，错误信息经 `errorRedactor` 脱敏后展示。
- `urlLinkify.ts`：URL 链接化 — 纯文本 URL 转可点击 `<a>` 标签（noopener noreferrer 安全属性）。
