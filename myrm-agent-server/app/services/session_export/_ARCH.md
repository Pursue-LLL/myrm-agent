# session_export 模块架构

Interactive Single-File HTML Exporter and Gist Share Bridge Service.

## 架构概述

提供全量会话高保真交互式单文件 HTML 编译打包、敏感凭证智能检测与自动脱敏、以及一键生成只读 Web 分享链接服务。零外部网络依赖，支持离线双击打开、代码块一键复制、思考推理折叠卡片与实时检索。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `export_types.py` | 核心模型 | 纯领域模型定义（ExportTheme（`system` / `light` / `dark`，其余取值在模型处被拒绝，到不了页面）, ExportHtmlOptions, RedactionSummary, InteractiveHtmlExportResult, ShareLinkRequest, ShareLinkResponse 等） | ✅ |
| `secret_redactor.py` | 核心引擎 | 正则识别并脱敏 API Keys、JWT/Bearer Tokens、密码字段与内网私有 IP；摘要可跨任意多段文字合并，同一类凭据只出一条（`merge_summaries` / `detect_secrets_in`），导出与预检共用这一条聚合路径 | ✅ |
| `interactive_html_compiler.py` | 核心编译器 | 将多轮消息编译打包为自包含单 HTML 文件（内嵌响应式 CSS、浅 / 深两套 CSS 变量配色、全局 `:focus-visible` 聚焦环、主题切换、思考折叠、ToolCall 折叠与代码复制 Vanilla JS；每个 `pre` 是其复制按钮的定位容器，工具栏在窄屏换行；两套配色的文字对比度 ≥ 4.5、输入框边缘与聚焦环 ≥ 3，由 `tests/services/session_export` 钉住；`system` 主题没有单独规则，沿用浅色配色） | ✅ |
| `session_export_service.py` | 应用服务 | 读取已存会话（不存在抛 `SessionNotFoundError`，读库失败原样上抛，不拼出一份看起来正常的会话）、按会话 id 预检其中的凭据（扫描在线程里跑，不占事件循环）、HTML 编译以及 HMAC 只读分享链接生成 | ✅ |
| `__init__.py` | 门面 | 导出服务单例与领域模型 | ✅ |
