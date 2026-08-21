# services/memory/imports 模块架构

## 架构概述

记忆导入 adapter 目录、服务端绑定导入审查会话、纯导入计划校验、关系型导入批次/条目事务账本、崩溃安全回滚 journal、导入后自动诊断、账本权威回滚预演与基于 exact mutation refs 的精准回滚、回滚后完整性探针、画像 revision 乐观并发保护、Integration Memory 业务服务与 Integration Sync Daemon、MCP Server→IntegrationProvider 桥接。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `import_adapter_registry.py` | 核心 | 记忆导入 adapter 目录。为导入 dry-run 和个人大脑指挥中心提供一致的来源支持状态，标记 native-json/myrm-archive/agentmemory/claude-code/hermes/openclaw/cursor/codex/chatgpt/gbrain ready 与其他来源计划或缺失状态 | ✅ |
| `import_adapter_utils.py` | 辅助 | 导入适配器共享工具。集中 `build_result`、`unsupported_result`、`object_dict`、`text` 和 warning code 常量 | ✅ |
| `import_adapters.py` | 核心 | 记忆导入 dry-run dispatcher。Wizard 五源 `_MIGRATION_SOURCE_TO_ADAPTER`（含 chatgpt upload-only）；Memory Center 手动导入仍支持 cursor_rules/mem0 等；`_source` 标签优先于 Markdown 启发式 | ✅ |
| `import_agentmemory.py` | 辅助 | AgentMemory 导入解析器。处理 agentmemory export 格式解析 | ✅ |
| `import_chatgpt.py` | 辅助 | ChatGPT 竞品导入解析器。解析 ChatGPT conversations.json 的 tree-based mapping 结构到 episodic 记忆类型 | ✅ |
| `import_claude_code.py` | 辅助 | Claude Code JSONL 导入解析器。调用 claude_code_parser 消费 JSONL transcript | ✅ |
| `import_claude_code_parser.py` | 辅助 | Claude Code JSONL transcript 解析器。逐行解析 JSONL entry、id 去重（last-write-wins）、entry 分类（user/assistant/summary/system）、对话 turn 重建、summary→semantic / turn→episodic / error→procedural 映射 | ✅ |
| `import_codex.py` | 辅助 | Codex 竞品导入解析器。解析 Codex instructions 和 settings 到原生记忆类型 | ✅ |
| `import_cursor.py` | 辅助 | Cursor 竞品导入解析器。解析 Cursor rules 和 settings 到原生记忆类型 | ✅ |
| `import_gbrain.py` | 辅助 | gbrain 竞品导入解析器。解析 gbrain export 的 Markdown+YAML frontmatter 页面，按 page type 映射到 profile/episodic/semantic 三桶 | ✅ |
| `import_hermes.py` | 辅助 | Hermes 记忆车道解析器。MEMORY.md/USER.md → semantic/profile；SOUL/AGENTS 由 migration 指令车道处理 | ✅ |
| `import_ledger.py` | 核心 | 记忆导入批次/条目事务账本服务。维护 confirmed/rollback_in_progress/rolled_back/partial/rollback_failed 批次状态和 imported/skipped/rolled_back/conflict/missing/rollback_failed 条目状态，保存内容盲回滚事实、结构化 warning code、rollback health counter 和自动诊断摘要 | ✅ |
| `import_mem0.py` | 辅助 | Mem0 竞品导入解析器。将 Mem0 扁平 memory 列表映射为原生 semantic 桶 | ✅ |
| `import_myrm_archive.py` | 辅助 | Myrm Archive 导入解析器。处理 Myrm Memory Archive 的 memory section | ✅ |
| `import_native_json.py` | 辅助 | Native JSON 导入解析器。处理原生 JSON 格式导入映射 | ✅ |
| `import_openclaw.py` | 辅助 | OpenClaw 竞品导入解析器。解析 OpenClaw sessions 和 memory entries | ✅ |
| `import_plur.py` | 辅助 | PLUR 竞品导入解析器。解析 PLUR local YAML/JSON engrams 并映射到 profile 与 semantic 记忆分桶 | ✅ |
| `import_rollback.py` | 核心 | 记忆导入回滚辅助。封装账本条目分类、profile revision 并发冲突检测、结构化 warning 生成、普通记忆 exact mutation refs 回滚和 profile 乐观回滚 | ✅ |
| `import_session_data.py` | 辅助 | 记忆导入会话数据转换。负责 payload 指纹、纯导入计划、normalized data JSON 转换、导入 metadata 注入、transaction item 构建和 profile 导入前后 revision snapshot 采集 | ✅ |
| `import_session_models.py` | 辅助 | 记忆导入会话 DTO。定义 confirm、rollback preview 和含 exact ref drilldown / integrity status 的 rollback result 服务层返回对象 | ✅ |
| `import_sessions.py` | 核心 | 记忆导入审查会话编排服务。持久化 dry-run 结果、payload hash、过期时间、normalized data 和 plan hash，确认时只接受 dry_run_id 并校验计划一致性，协调导入批次审计、迁移来源、关系型 item-level transaction ledger、崩溃安全回滚 journal、账本权威回滚预演、profile revision 冲突保护、回滚后完整性探针、导入后诊断结果回写、运行就绪合同（readiness status/issues + **`recheck_facts` SSOT**）回写、**`resolve_live_import_readiness` live 重算**、首轮执行结果锚点（first-turn outcome）回写和保留窗口清理指标 | ✅ |
| `integration_memory.py` | 核心 | Integration Memory 业务服务。封装框架层 IntegrationFetcher/TreeManager/Summariser，提供 sync/browse/status/remove facade 和类型安全 DTO（IntegrationStatusSnapshot/IntegrationTreeNodeDTO）供 API 层消费 | ✅ |
| `integration_sync_daemon.py` | 核心 | Integration Sync Daemon — 基于 APScheduler 的后台定时同步守护进程。每次触发时动态加载用户 MCP 配置（含 Control Plane 推送的 org MCP，经 `merge_org_mcp_configs` 合并），将符合条件的 MCP Server 注册为 MCPBridgeProvider，然后调用 IntegrationMemoryService.sync_all() 保持知识源新鲜 | ✅ |
| `mcp_bridge_provider.py` | 核心 | MCPBridgeProvider — 将任意 MCP Server 桥接为 IntegrationProvider。通过 DI 注入 MCPConnection，自动探测 fetch 工具并将结果转换为 IntegrationLeaf | ✅ |
