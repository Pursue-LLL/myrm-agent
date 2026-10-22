# session_export 模块架构

Interactive Single-File HTML Exporter and Gist Share Bridge Service.

## 架构概述

提供全量会话高保真交互式单文件 HTML 编译打包、敏感凭证智能检测与自动脱敏、以及一键生成只读 Web 分享链接服务。零外部网络依赖，支持离线双击打开、代码块一键复制、思考推理折叠卡片与实时检索。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `export_types.py` | 核心模型 | 纯领域模型定义（ExportHtmlOptions, RedactionSummary, InteractiveHtmlExportResult, ShareLinkRequest, ShareLinkResponse 等） | ✅ |
| `secret_redactor.py` | 核心引擎 | 正则识别并脱敏 API Keys、JWT/Bearer Tokens、密码字段与内网私有 IP，输出脱敏统计摘要 | ✅ |
| `interactive_html_compiler.py` | 核心编译器 | 将多轮消息编译打包为自包含单 HTML 文件（内嵌响应式 CSS、主题切换、思考折叠、ToolCall 折叠与代码复制 Vanilla JS） | ✅ |
| `session_export_service.py` | 应用服务 | 协调会话数据提取、脱敏处理、HTML 编译以及 HMAC 只读分享链接生成 | ✅ |
| `__init__.py` | 门面 | 导出服务单例与领域模型 | ✅ |
