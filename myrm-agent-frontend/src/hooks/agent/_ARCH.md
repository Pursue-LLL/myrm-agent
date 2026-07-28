# hooks/agent/

智能体配置、编辑、预设与资源选择。

| 文件 | 职责 |
|------|------|
| `useAgentConfigPanel.ts` | AgentConfigPanel 业务编排 |
| `useAgentEditor.ts` | Agent 编辑表单 |
| `useAgentGallery.ts` | Agent gallery |
| `usePresetAgent.ts` | 预设智能体 |
| `useAgentResources.ts` | 资源选择解析 |
| `useAgentName.ts` | agent_id → 显示名 |
| `useCLIAgent.ts` | 外部 CLI agent |
| `useAgentReadiness.ts` | Per-agent readiness SWR hook (5min polling) |
| `useSkillDiscovery.ts` | 技能发现 |
| `config-panel/` | 配置变更检测与 save handler | [_ARCH.md](config-panel/_ARCH.md) |

消费者：`chat-window/agent-config-panel/`、Settings ai-core、kanban。
