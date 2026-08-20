# hooks/agent/

智能体配置、编辑、预设与资源选择。

| 文件 | 职责 |
|------|------|
| `useAgentConfigPanel.ts` | AgentConfigPanel 业务编排 |
| `useAgentEditor.ts` | Settings Agent 编辑：load/save `skill_configs`（含 `instance_name`）、`hasChanges` 与 Chat 面板对齐 |
| `useAgentGallery.ts` | Agent gallery |
| `usePresetAgent.ts` | 预设智能体 |
| `useAgentResources.ts` | 资源选择解析 |
| `useAgentName.ts` | agent_id → 本地化显示名（内置 agent 走 `getBuiltinAgentName`） |
| `useCLIAgent.ts` | 外部 CLI agent |
| `useAgentReadiness.ts` | Per-agent readiness SWR hook (5min polling) |
| `useSkillDiscovery.ts` | 技能发现、预览、安装、卸载及 `skill_pool_updated` 实时热同步 |
| `config-panel/` | 配置变更检测与 save handler | [_ARCH.md](config-panel/_ARCH.md) |

消费者：`chat-window/agent-config-panel/`、Settings ai-core、kanban。
