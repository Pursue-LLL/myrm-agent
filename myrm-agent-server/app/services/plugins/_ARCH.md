# services/plugins/

## 架构概述

Agent Plugins 1.0.0 导入编排（业务层）。消费框架层解析器 `myrm_agent_harness.agent.plugins`，将技能与 MCP 配置持久化到业务存储并绑定 Agent。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `import_service.py` | 门面 | 插件导入编排门面：ZIP 解析包装（archive security → 结构化错误）、预览构建（含同名冲突标记）、confirm 落盘编排（同名技能原位升级 + MCP 落盘）、`_load_existing_skill_ids` 冲突 SSOT，并 re-export 会话/模型/持久化符号 | ✅ |
| `_models.py` | 模型 | `PluginImportSession` / `PluginConfirmItem` 业务层 DTO | ✅ |
| `_staging.py` | 存储 | `PluginStaging` 导入会话持久化（pickle + 24h TTL 清理） | ✅ |
| `_mcp_persist.py` | 持久化 | MCP 落盘合并（`{"mcpConfigs": [...]}` + name 去重 + disabled 默认）、`invalidate_user_configs_cache` 失效、Agent 绑定 skill_ids+mcp_ids、secret 引用解析与 `required_secret_keys` 收集 | ✅ |

## 设计原则

- **离线导入**：全程零 LLM 调用，仅磁盘 I/O。
- **逐组件失败隔离**：单个无效 skill/MCP 不中止整个导入。
- **安全默认**：MCP headers 不落明文（已是 `{{secret:KEY}}` 引用的值原样保留，其余值映射为 `{{secret:KEY}}` 引用）；env/cwd 写入 `extra_params`（与前端解析器、harness MCPConfig 结构一致）；MCP 默认 disabled，用户显式启用。
- **Scoped Secret Injection**：导入时把插件声明的 `env_key_names` 写入 MCP 条目 `required_secrets`，运行时仅从 Agent 密钥库注入这些 key（`mcp_runtime_prepare` 的 minimal-privilege 契约），不注入全量环境变量；confirm 返回去重后的 `required_secret_keys`（env_key_names + headers 引用键名），前端在导入成功提示中引导用户在「智能体密钥」配置对应密钥。
- **mcpServers 存储契约**：`mcpServers` UserConfig 始终以 `{"mcpConfigs": [...]}` 结构读写（与前端 `useConfigStore`、运行时 `config_loader._coerce_config_dict` + `config_parsers.extract_mcp_configs` 一致）。confirm 落盘前读取并合并已有配置（兼容历史裸 list payload），**绝不允许导入覆盖用户已有 MCP 配置**；写入成功后调用 `invalidate_user_configs_cache()` 使 30s TTL 缓存立即失效。
- **技能安全扫描**：预览阶段对每个 skill 内容运行 `SkillSecurityValidator`，`security_issues` 随预览返回；confirm 阶段重新扫描，未通过的 skill 即使标记 install 也会被跳过（预览状态不可信，防御纵深）。扫描器自身异常按 **fail-closed** 处理（视为不安全并跳过），避免崩溃或静默放行。
- **超长技能隔离**：skill 内容超过 `SkillStore.MAX_SKILL_CONTENT_CHARS`（64 KB）时，预览携带 `oversized_content` 标记，confirm 阶段直接跳过（不入库、不向量化）。与框架层 `save_skills_batch` 的硬校验对齐，避免超大 skill 因向量化静默失败而"已入库但检索不到"。
- **同名技能升级（冲突处理）**：`_load_existing_skill_ids` 在预览与 confirm 时各查询一次 active 技能名映射（`name → skill_id`）。预览对已存在同名技能标记 `conflict`，UI 提供"覆盖/跳过"决策；confirm 时以**服务端重新查询**的映射为权威（不信任前端回传），同名技能一律原位升级——复用原 `skill_id` + `EvolutionType.DERIVED` lineage，确保技能库永不出现同名重复记录。与批量导入 `batch_import` 的 conflict+replace 模式对齐，但仅保留 replace/skip 两种决策（插件的技能路径含插件名，rename 会破坏路径一致性，故不引入 rename_cow）。
- **Agent 绑定**：绑定 Agent 时通过单次 `AgentUpdate` 原子追加 skill_ids 与 mcp_ids（去重），缺失 agent 与重复 id 静默容忍。
- **MCP 去重**：confirm 落盘前与现有 `mcpServers` 按 name 去重，重名 server 被跳过且不计入 `imported_servers`、不绑定 Agent（计数/绑定仅反映实际落盘项）。合并基于已持久化的配置（`{"mcpConfigs": [...]}`，兼容 legacy 裸 list），保证导入仅追加、永不丢弃用户已有服务器。
- **会话清理**：`PluginStaging` 通过 `cleanup_expired_sessions`（线程内执行同步清理）在后台删除超过 24h 的无主会话，防止磁盘堆积。
