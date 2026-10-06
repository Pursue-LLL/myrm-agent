# services/plugins/

## 架构概述

Agent Plugins 1.0.0 导入编排（业务层）。消费框架层解析器 `myrm_agent_harness.agent.plugins`，将技能（走标准隔离安装管线）、MCP 配置与专家（Agent profile）持久化到业务存储并绑定 Agent。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包入口 | 统一导出插件服务模块公开 API | ✅ |
| `import_service.py` | 门面 | 导入编排门面：ZIP 解析包装（archive security → 结构化错误）、`confirm_plugin_import`（技能安装 → bundled 文件 → MCP 落盘 → 专家持久化 → 可选绑定既有专家；返回计数、逐专家结果 `agents` 与逐组件 `failures`）、`list_installed_plugins` / `uninstall_plugin`，并 re-export 会话/模型/预览/上下文符号 | ✅ |
| `_models.py` | 模型 | `PluginImportSession` / `PluginConfirmItem` / `ComponentFailure` 业务层 DTO | ✅ |
| `_preview.py` | 预览 | `build_preview_result`（技能/连接器/专家的冲突、阻断、未解析引用、tighten-only 生效值，`deployment` 部署开关）、`compute_capability_diff`（升级权限扩张分析）、模板物料容量诊断 | ✅ |
| `_preview_context.py` | 上下文 | `PreviewContext` / `load_preview_context`：预览与 confirm 共用的安装状态事实（已装技能、已配置连接器、同名专家、部署限制）；失败降级为空事实并记录 WARNING | ✅ |
| `_gates.py` | 门禁 | 预览与 confirm 共用的安装前判定：`scan_skill_security`（fail-closed）、`skill_block_reason` / `server_block_reason`（部署限制、超长内容）与 `BLOCK_*` 码 | ✅ |
| `_skill_persist.py` | 持久化 | `install_plugin_skills`：技能经 `market_service.install_files`（生命周期脚本门禁 → 全文件安全评分 → 版本降级保护 → 原子提升）安装并挂载到技能目录，返回规范 skill id；逐技能失败隔离；清理旧版导入遗留的无文件记录 | ✅ |
| `agent_surface.py` | 专家面 | 专家面 SSOT：`AgentBase` 47 个字段的处置表（CARRY/REFERENCE/DISPLAY/DERIVE/DROP，默认拒绝）、`import_agent_fields`（tighten-only：工具限于默认授权、循环预算只降不升、安全字段一律丢弃）、`profile_to_plugin_agent`（导出方向投影） | ✅ |
| `_agent_plan.py` | 规划 | 专家绑定计划（纯函数）：逐专家显式绑定 + 入口专家隐式兜底、隐式团队、子专家先于主专家的创建顺序、环边剔除、未解析引用清单 | ✅ |
| `_agent_persist.py` | 持久化 | `persist_imported_agents`：按计划写入专家；同名策略（`install` 建副本 "X (imported[ n])"、`replace` 原位更新用户自有专家并自动快照、内置专家永不替换）；失败回滚本次新建的专家；逐专家结果与 `ComponentFailure` | ✅ |
| `template_workspace.py` | 物料 | 模板物料存储格式 SSOT：`encode_template_files`（容量护栏，跳过而非截断）、`decode_template_files`、`materialize_template_workspace_files`（新会话 JIT 释放，防路径穿越、不覆盖已有文件） | ✅ |
| `_staging.py` | 存储 | `PluginStaging` 导入会话持久化（pickle + 24h TTL 清理） | ✅ |
| `_mcp_persist.py` | 持久化 | MCP 落盘合并（`{"mcpConfigs": [...]}` + name 去重 + disabled 默认）、`invalidate_user_configs_cache` 失效、`_collect_server_configs`（部署与缺失产物阻断，作为 `ComponentFailure` 报告）、Agent 绑定 skill_ids+mcp_ids、secret 引用解析与 `required_secret_keys` 收集；`_server_to_config_dict` 将 `plugin_name`/`plugin_root`/`data_root` 嵌入 `extra_params`；卸载相关 `_remove_plugin_mcp_servers` 与 `_unbind_plugin_from_agents` | ✅ |
| `_plugin_files.py` | 存储 | bundled 插件文件持久化：`server_needs_bundled_files`、`persist_plugin_files`（写入 `{data_dir}/plugins/{name}/` 与 `{name}_data/`）、`remove_plugin_files`、`plugin_dir_exists`/`is_safe_plugin_name` | ✅ |
| `_uninstall.py` | 生命周期 | `list_installed_plugins`（按 `extra_params.plugin_name` 溯源分组，含 `server_meta` 启用状态与能力）与 `uninstall_plugin`（四维清退） | ✅ |

## 设计原则

- **离线导入**：全程零 LLM 调用，仅磁盘 I/O。
- **逐组件失败隔离**：单个无效 skill/MCP 不中止整个导入。
- **安全默认**：MCP headers 不落明文（已是 `{{secret:KEY}}` 引用的值原样保留，其余值映射为 `{{secret:KEY}}` 引用）；env/cwd 写入 `extra_params`（与前端解析器、harness MCPConfig 结构一致）；MCP 默认 disabled，用户显式启用。
- **Scoped Secret Injection**：导入时把插件声明的 `env_key_names` 写入 MCP 条目 `required_secrets`，运行时仅从 Agent 密钥库注入这些 key（`mcp_runtime_prepare` 的 minimal-privilege 契约），不注入全量环境变量；confirm 返回去重后的 `required_secret_keys`（env_key_names + headers 引用键名），前端在导入成功提示中引导用户在「智能体密钥」配置对应密钥。
- **mcpServers 存储契约**：`mcpServers` UserConfig 始终以 `{"mcpConfigs": [...]}` 结构读写（与前端 `useConfigStore`、运行时 `config_loader._coerce_config_dict` + `config_parsers.extract_mcp_configs` 一致）。confirm 落盘前读取并合并已有配置（兼容历史裸 list payload），**绝不允许导入覆盖用户已有 MCP 配置**；写入成功后调用 `invalidate_user_configs_cache()` 使 30s TTL 缓存立即失效。
- **Bundled 文件持久化**：接受含 bundled stdio server（`./` 命令或 `${PLUGIN_ROOT}`/`${PLUGIN_DATA}` 占位符）的插件时，将插件文件树（`plugin.json`/`mcp.json`/`bin/*` 等非 skill 文件，来自框架层 `PluginParseResult.files`）持久化到 `{data_dir}/plugins/{plugin_name}/` 与 `{name}_data/` 两目录，并把绝对路径写入各 MCP 条目 `extra_params.plugin_root` / `data_root`（运行时由 harness `placeholders.resolve_stdio_launch` 展开）。目录名经过 `is_safe_plugin_name` 校验，杜绝路径穿越。
- **Provenance 溯源**：每个插件导入的 MCP 条目在 `extra_params.plugin_name` 记录来源插件名，作为卸载定位与「已安装插件」列表分组的 SSOT；用户手动配置的 server 无该标记，永不混入插件管理视图。
- **卸载生命周期（四维彻底清退）**：`uninstall_plugin` 按 `plugin_name` 移除全部插件 MCP 条目（保留用户自建 server）、从所有 Agent 的 `mcp_ids` 解绑对应 server 名（`UnitOfWork` 原子更新）、执行 Tool Registry 内存即时注销（`evict_skill_safety_metadata`）、级联下线/暂停关联的后台 Cron 定时任务、安全删除插件文件与数据目录；全维度清退由统一流水线编排，各环节异常安全隔离并记录日志，保证插件完全彻底离场、无任何暗线与孤儿残留。**导入的技能保留在技能库**，由技能管理页独立管理（卸载仅清理 MCP 配置/Agent 绑定/文件，避免误删用户已定制技能）。
- **技能与市场同管线**：插件技能与市场技能走同一条隔离安装管线（`market_service.install_files`）：生命周期脚本门禁 → 安全评分（扫描**全部**文本文件，含 `scripts/`）→ 版本降级保护 → 原子提升并写 `origin.json`/`receipt.json`。安装结果是真实文件（`scripts/`、`references/` 完整可读、可装配），挂载到技能目录并取规范 id（`local::<hash>`），专家按该 id 绑定；被拒绝的技能不留任何残留。预览阶段的内容扫描与 confirm 重新判定共用 `_gates`（预览状态不可信，防御纵深），扫描器自身异常按 fail-closed 处理。
- **部署感知**：`deployment_capabilities.allows_local_skills` 为 false 的部署不安装技能，`settings.mcp.allow_stdio` 为 false 的部署（云沙箱）不导入 stdio 连接器；预览通过 `blocked_reason` 与 `deployment` 提前呈现，confirm 以服务端重新读取的事实为准并把被拒组件作为 `failures` 报告（而不是静默跳过或整体 500）。超长 SKILL.md（`SkillStore.MAX_SKILL_CONTENT_CHARS`）同样以 `oversized_content` 阻断。
- **同名处理**：技能——预览按名称对已装技能标记 `conflict`；`install` 在版本不低于已装版本时原位升级，降级被版本保护以 `DOWNGRADE_BLOCKED` 拒绝，`replace` 显式允许降级。专家——同名时 `install` 创建 "X (imported[ n])" 副本、从不触碰用户已有专家；`replace` 原位更新用户自有专家（保持身份与历史，并自动保存上一版快照，内置专家永不替换）。未给出决策的专家不会被导入。
- **专家导入（tighten-only）**：专家字段按处置表默认拒绝；导入只会收紧——内置工具限于默认授权（`web_search`/`memory`/`structured_clarify`，其余作为 `withheld_tools` 报告）、`max_iterations` 只降不升（5–50）、`security_overrides` / `default_security_preset` / `trusted_desktop_apps` / `prompt_mode` 等安全与机器本地字段一律丢弃。绑定逐专家显式（入口专家未声明技能/连接器时兜底获得本包安装的全部），入口专家未声明 `subagents` 时隐式带领其余专家，存在子专家的主专家 `agent_type="team"`。创建顺序子专家优先，环边剔除；任一写入失败回滚本次新建的专家。
- **MCP 去重**：confirm 落盘前与现有 `mcpServers` 按 name 去重，重名 server 被跳过且不计入 `imported_servers`、不绑定 Agent（计数/绑定仅反映实际落盘项）。合并基于已持久化的配置（`{"mcpConfigs": [...]}`，兼容 legacy 裸 list），保证导入仅追加、永不丢弃用户已有服务器。
- **会话清理**：`PluginStaging` 通过 `cleanup_expired_sessions`（线程内执行同步清理）在后台删除超过 24h 的无主会话，防止磁盘堆积。
- **沙箱能力模型与升级权限扩张防护**：
  导入阶段解析插件声明与静态推导的 `PluginCapabilityTier`（read_only、fs_read、fs_write、network、shell_exec、destructive）。
  针对覆盖更新安装场景，通过 `compute_capability_diff` 比对已安装版本与新包能力，检测是否包含新增高危提权行为（如增加 shell_exec、destructive 或未授权 network 访问），在 UI 显式呈递权限徽章与高危警告，阻断恶意插件的“先以安全版本入库、后以静默升级提权越权”攻击链。
- **模板物料容量护栏与沙箱隔离下发**：插件 `ai.myrm/workspace/` 资产作为开箱即用物料注入**入口专家**的 `engine_params.template_workspace_files`（文本或 `base64:` 二进制）。单文件上限 `MAX_TEMPLATE_FILE_BYTES`（1MB）、累计上限 `MAX_TOTAL_TEMPLATE_BYTES`（5MB），超限文件被跳过（不截断，后续更小的文件仍可入选），预览以 Warning 诊断透传且与落盘判定一致（同一 `encode_template_files`）。新会话启动时由 `workspace_resolve.py` 在会话专属工作区 JIT 释放，`Path.is_relative_to` 防路径穿越且从不覆盖已有文件。
