# services/plugins/

## 架构概述

Agent Plugins 1.0.0 导入编排（业务层）。消费框架层解析器 `myrm_agent_harness.agent.plugins`，将技能与 MCP 配置持久化到业务存储并绑定 Agent。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包入口 | 统一导出插件服务模块公开 API | ✅ |
| `import_service.py` | 门面 | 插件导入编排门面：ZIP 解析包装（archive security → 结构化错误）、预览构建（含同名冲突标记）、confirm 落盘编排（同名技能原位升级 + MCP 落盘 + bundled 文件持久化）、`list_installed_plugins`（按 plugin_name 溯源分组列出已导入插件，含每个 server 的 `enabled` 状态 `server_meta`，供插件管理 UI 展示启用状态）、`uninstall_plugin`（卸载：删 MCP 条目 + 解绑 Agent + 删文件）、`_load_existing_skill_ids` 冲突 SSOT，并 re-export 会话/模型/持久化符号 | ✅ |
| `_models.py` | 模型 | `PluginImportSession` / `PluginConfirmItem` 业务层 DTO | ✅ |
| `_preview.py` | 预览 | 插件导入预览构建与离线安全校验：`build_preview_result`、`compute_capability_diff`（升级权限扩张分析）、`scan_skill_security`、`skill_content_too_large`、模板物料容量扫描与 diagnostics 诊断透传 | ✅ |
| `_staging.py` | 存储 | `PluginStaging` 导入会话持久化（pickle + 24h TTL 清理） | ✅ |
| `_agent_persist.py` | 持久化 | Agent 团队与物料持久化：`persist_imported_agents`（两阶段创建子智能体与入口智能体、自动绑定 subagent_ids 与 workspace 模板物料）、`sanitize_imported_security_overrides`（fail-closed 安全越权清洗）、模板物料容量安全护栏（`MAX_TEMPLATE_FILE_BYTES = 1MB`、`MAX_TOTAL_TEMPLATE_BYTES = 5MB`） | ✅ |
| `_mcp_persist.py` | 持久化 | MCP 落盘合并（`{"mcpConfigs": [...]}` + name 去重 + disabled 默认）、`invalidate_user_configs_cache` 失效、Agent 绑定 skill_ids+mcp_ids、secret 引用解析与 `required_secret_keys` 收集；`_server_to_config_dict` 将 `plugin_name`/`plugin_root`/`data_root` 嵌入 `extra_params`；卸载相关 `_remove_plugin_mcp_servers`（按 plugin_name 移除 MCP 条目）与 `_unbind_plugin_from_agents`（从 Agent `mcp_ids` 解绑） | ✅ |
| `_plugin_files.py` | 存储 | bundled 插件文件持久化：`server_needs_bundled_files`（server 是否需要随插件发布文件）、`persist_plugin_files`（写入 `{data_dir}/plugins/{name}/` 与 `{name}_data/`）、`remove_plugin_files`（删除两目录）、`plugin_dir_exists`/`is_safe_plugin_name`（列表/卸载时校验与探测） | ✅ |

## 设计原则

- **离线导入**：全程零 LLM 调用，仅磁盘 I/O。
- **逐组件失败隔离**：单个无效 skill/MCP 不中止整个导入。
- **安全默认**：MCP headers 不落明文（已是 `{{secret:KEY}}` 引用的值原样保留，其余值映射为 `{{secret:KEY}}` 引用）；env/cwd 写入 `extra_params`（与前端解析器、harness MCPConfig 结构一致）；MCP 默认 disabled，用户显式启用。
- **Scoped Secret Injection**：导入时把插件声明的 `env_key_names` 写入 MCP 条目 `required_secrets`，运行时仅从 Agent 密钥库注入这些 key（`mcp_runtime_prepare` 的 minimal-privilege 契约），不注入全量环境变量；confirm 返回去重后的 `required_secret_keys`（env_key_names + headers 引用键名），前端在导入成功提示中引导用户在「智能体密钥」配置对应密钥。
- **mcpServers 存储契约**：`mcpServers` UserConfig 始终以 `{"mcpConfigs": [...]}` 结构读写（与前端 `useConfigStore`、运行时 `config_loader._coerce_config_dict` + `config_parsers.extract_mcp_configs` 一致）。confirm 落盘前读取并合并已有配置（兼容历史裸 list payload），**绝不允许导入覆盖用户已有 MCP 配置**；写入成功后调用 `invalidate_user_configs_cache()` 使 30s TTL 缓存立即失效。
- **Bundled 文件持久化**：接受含 bundled stdio server（`./` 命令或 `${PLUGIN_ROOT}`/`${PLUGIN_DATA}` 占位符）的插件时，将插件文件树（`plugin.json`/`mcp.json`/`bin/*` 等非 skill 文件，来自框架层 `PluginParseResult.files`）持久化到 `{data_dir}/plugins/{plugin_name}/` 与 `{name}_data/` 两目录，并把绝对路径写入各 MCP 条目 `extra_params.plugin_root` / `data_root`（运行时由 harness `placeholders.resolve_stdio_launch` 展开）。目录名经过 `is_safe_plugin_name` 校验，杜绝路径穿越。
- **Provenance 溯源**：每个插件导入的 MCP 条目在 `extra_params.plugin_name` 记录来源插件名，作为卸载定位与「已安装插件」列表分组的 SSOT；用户手动配置的 server 无该标记，永不混入插件管理视图。
- **卸载生命周期（四维彻底清退）**：`uninstall_plugin` 按 `plugin_name` 移除全部插件 MCP 条目（保留用户自建 server）、从所有 Agent 的 `mcp_ids` 解绑对应 server 名（`UnitOfWork` 原子更新）、执行 Tool Registry 内存即时注销（`evict_skill_safety_metadata`）、级联下线/暂停关联的后台 Cron 定时任务、安全删除插件文件与数据目录；全维度清退由统一流水线编排，各环节异常安全隔离并记录日志，保证插件完全彻底离场、无任何暗线与孤儿残留。**导入的技能保留在技能库**，由技能管理页独立管理（卸载仅清理 MCP 配置/Agent 绑定/文件，避免误删用户已定制技能）。
- **技能安全扫描**：预览阶段对每个 skill 内容运行 `SkillSecurityValidator`，`security_issues` 随预览返回；confirm 阶段重新扫描，未通过的 skill 即使标记 install 也会被跳过（预览状态不可信，防御纵深）。扫描器自身异常按 **fail-closed** 处理（视为不安全并跳过），避免崩溃或静默放行。
- **超长技能隔离**：skill 内容超过 `SkillStore.MAX_SKILL_CONTENT_CHARS`（64 KB）时，预览携带 `oversized_content` 标记，confirm 阶段直接跳过（不入库、不向量化）。与框架层 `save_skills_batch` 的硬校验对齐，避免超大 skill 因向量化静默失败而"已入库但检索不到"。
- **同名技能升级（冲突处理）**：`_load_existing_skill_ids` 在预览与 confirm 时各查询一次 active 技能名映射（`name → skill_id`）。预览对已存在同名技能标记 `conflict`，UI 提供"覆盖/跳过"决策；confirm 时以**服务端重新查询**的映射为权威（不信任前端回传），同名技能一律原位升级——复用原 `skill_id` + `EvolutionType.DERIVED` lineage，确保技能库永不出现同名重复记录。与批量导入 `batch_import` 的 conflict+replace 模式对齐，但仅保留 replace/skip 两种决策（插件的技能路径含插件名，rename 会破坏路径一致性，故不引入 rename_cow）。
- **Agent 绑定**：绑定 Agent 时通过单次 `AgentUpdate` 原子追加 skill_ids 与 mcp_ids（去重），缺失 agent 与重复 id 静默容忍。
- **MCP 去重**：confirm 落盘前与现有 `mcpServers` 按 name 去重，重名 server 被跳过且不计入 `imported_servers`、不绑定 Agent（计数/绑定仅反映实际落盘项）。合并基于已持久化的配置（`{"mcpConfigs": [...]}`，兼容 legacy 裸 list），保证导入仅追加、永不丢弃用户已有服务器。
- **会话清理**：`PluginStaging` 通过 `cleanup_expired_sessions`（线程内执行同步清理）在后台删除超过 24h 的无主会话，防止磁盘堆积。
- **沙箱能力模型与升级权限扩张防护**：
  导入阶段解析插件声明与静态推导的 `PluginCapabilityTier`（read_only、fs_read、fs_write、network、shell_exec、destructive）。
  针对覆盖更新安装场景，通过 `compute_capability_diff` 比对已安装版本与新包能力，检测是否包含新增高危提权行为（如增加 shell_exec、destructive 或未授权 network 访问），在 UI 显式呈递权限徽章与高危警告，阻断恶意插件的“先以安全版本入库、后以静默升级提权越权”攻击链。
- **模板物料容量护栏与沙箱隔离下发**：插件 `workspace/` 与 `template_files/` 资产作为开箱即用物料注入 Agent 的 `engine_params.template_workspace_files`。单文件上限 `MAX_TEMPLATE_FILE_BYTES`（1MB）、累计总容量上限 `MAX_TOTAL_TEMPLATE_BYTES`（5MB），超限文件安全截断并在预览时透传为 Warning 诊断，根除 SQLite 单行膨胀与反序列化 OOM。新会话启动时由 `workspace_resolve.py` 在当前会话专属沙箱安全 JIT 释放，并通过 `Path.is_relative_to` 绝对防御路径穿越。
