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
- `imeUtils.ts`：输入法组合输入守卫 — `isImeComposing` 统一判断 `nativeEvent.isComposing`、`event.isComposing`、`key === 'Process'` 与 `keyCode === 229`，保障 Windows/macOS/iOS/Android 输入法候选词确认不误触发消息提交。
- `titleUtils.ts`：会话标题消歧与序号自增 — `parseTitleIndex` 与 `disambiguateChatTitle` 纯函数，确保自动生成和重命名标题时保持全局列表唯一可辨（如自动追加 `(2)`、`(3)`）。
- `pathValidation.ts`：全平台路径规范与展示截断 — 支持 POSIX、Windows 盘符、Windows UNC 共享路径识别与反斜杠/正斜杠归一化，提供 `formatPathForDisplay` 智能居中省略截断。
- `skillUtils.ts`：Skill 多语言描述容灾守卫 — `resolveSkillDescription` 统一去除空串与空白，并在缺失时回退默认国际化文案，杜绝卡片与详情页空白。
- `typeUtils.ts`：安全字典与类型守卫 — `isRecord`、`asRecord` 与 `safeGet`，彻底防止服务端 dict-like 异常或嵌套层级缺失导致的 WebUI 运行时白屏与崩溃。
