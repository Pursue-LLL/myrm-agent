# services/plugins/

## 架构概述

Agent Plugins 1.0.0 导入编排（业务层）。消费框架层解析器 `myrm_agent_harness.agent.plugins`，将技能与 MCP 配置持久化到业务存储并绑定 Agent。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `import_service.py` | 模块 | 插件导入编排：ZIP 解析包装（archive security → 结构化错误）、`PluginStaging` 持久化会话、预览构建、confirm 落盘（skills → SkillStore INSTALLED 层 / MCP → mcpServers UserConfig disabled / agent 绑定 skill_ids+mcp_ids） | ✅ |

## 设计原则

- **离线导入**：全程零 LLM 调用，仅磁盘 I/O。
- **逐组件失败隔离**：单个无效 skill/MCP 不中止整个导入。
- **安全默认**：MCP headers 不落明文（映射为 `{{secret:KEY}}` 引用）；env/cwd 写入 `extra_params`（与前端解析器、harness MCPConfig 结构一致）；MCP 默认 disabled，用户显式启用。
- **技能安全扫描**：预览阶段对每个 skill 内容运行 `SkillSecurityValidator`，`security_issues` 随预览返回；confirm 阶段重新扫描，未通过的 skill 即使标记 install 也会被跳过（预览状态不可信，防御纵深）。
- **Agent 绑定**：绑定 Agent 时追加 skill_ids 与 mcp_ids，复用 `apply_agent_mcp_selection` 语义。
