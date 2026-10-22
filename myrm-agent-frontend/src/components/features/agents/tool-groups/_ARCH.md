# Semantic Tool Group & Zero-Terminal Config Suite 架构说明

## 1. 业务目标与降维价值
彻底破除极客 Agent 工具权限配置全靠在终端编写生涩 JSON5/YAML 配置文件导致普通办公用户望而却步被劝退的严重易用性硬伤。
对标 OpenClaw 2.0 tool group 概念，将数十个底层工具抽离降维为 6 大直观业务语义组：
1. **沙箱代码执行 (Runtime)**：`exec_command`, `python_interpreter`, `bash_session`, `kill_process`；
2. **本地工作区读写 (Filesystem)**：`read_file`, `list_directory`, `write_file`, `replace_file_content`；
3. **长效记忆沉淀 (Memory)**：`store_fact`, `recall_context`, `delete_profile`；
4. **全网知识检索 (Web)**：`search_web`, `fetch_url_content`, `browser_action`；
5. **界面交互卡片 (UI & Canvas)**：`render_card`, `ask_user_choice`, `paint_diagram`；
6. **外部通信网关 (Messaging)**：`send_channel_alert`, `invoke_peer_agent`, `webhook_post`。

## 2. 核心架构设计
- `semanticToolGroupTypes.ts`: 纯粹具体的强类型系统，零 `any`，定义语义组、细粒度工具、安全等级与配置编译模型；
- `semanticToolGroupRegistry.ts`: 6 大业务语义组标准元数据、4 大安全预设模板（严格安全、标准助理、全栈开发、自定义）及多维度安全评分与策略编译引擎；
- `useSemanticToolGroupStore.ts`: 基于 Zustand 的集中式响应状态机，支持一键切换预设、组级开关、细粒度工具独立授权微调、JSON 导入/导出与底层零终端同步；
- `SemanticToolGroupCard.tsx`: 现代化工业级交互卡片，集成安全指数仪表盘、风险标识徽章、细粒度工具折叠器与零终端配置 JSON 预览器。

## 3. 工程质量与安全红线守则
- **零 any 约束**：全量代码均使用严格强类型约束；
- **单文件行数受控**：各文件行数均严格保持在 300 行以内（远低于 400 行红线）；
- **零原生 emoji**：全部使用统一的 Lucide 矢量图标；
- **全括号与代码健壮性**：所有 `if` 均显式包裹 `{}`；
- **无障碍访问 a11y**：语义化 HTML 标签与严格 ARIA 标准。
