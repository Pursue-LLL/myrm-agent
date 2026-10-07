# hooks/agent/

智能体配置、编辑、预设与资源选择。

| 文件                     | 职责                                                                                                                                                                     |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `useAgentConfigPanel.ts` | AgentConfigPanel 业务编排                                                                                                                                                |
| `useAgentEditor.ts`      | Settings Agent 编辑：load/save `skill_configs`（含 `instance_name`）、`hasChanges` 与 Chat 面板对齐                                                                      |
| `useAgentGallery.ts`     | Agent gallery                                                                                                                                                            |
| `useAgentAiBuild.ts`     | 新建 Agent 页「描述你想要的 Agent」：流式读取草稿并只应用本机存在的技能/MCP/内置工具；失败只给本地化句（缺模型按 `model_not_configured` 单独提示），后端原文只写 console |
| `usePresetAgent.ts`      | 预设智能体                                                                                                                                                               |
| `useAgentResources.ts`   | 资源选择解析                                                                                                                                                             |
| `useAgentName.ts`        | agent_id → 本地化显示名（内置 agent 走 `getBuiltinAgentName`）                                                                                                           |
| `useAgentReadiness.ts`   | Per-agent readiness SWR hook (5min polling)                                                                                                                              |
| `useSkillDiscovery.ts`   | 技能发现、预览、安装、卸载及 `skill_pool_updated` 实时热同步                                                                                                             |
| `config-panel/`          | 配置变更检测与 save handler                                                                                                                                              | [_ARCH.md](config-panel/_ARCH.md) |

消费者：`chat-window/agent-config-panel/`、Settings ai-core、kanban。
