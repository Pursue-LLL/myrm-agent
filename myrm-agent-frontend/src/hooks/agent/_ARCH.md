# hooks/agent/

智能体配置、编辑、预设与资源选择。

| 文件                          | 职责                                                                                                                                                                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `useAgentConfigPanel.ts`      | AgentConfigPanel 业务编排：进入面板时加载技能 / MCP / 名册，保存弹窗配置，把当前配置（含 MCP 工具选择、浏览器与录制设置）保存为新智能体；已保存的智能体在 Settings 的智能体页编辑，对话面板不改它                              |
| `useAgentEditor.ts`           | Settings Agent 编辑：load/save `skill_configs`（含 `instance_name`）与 `hasChanges`                                                                                                                                            |
| `useAgentCommandBindings.ts`  | Settings Agent 编辑面板的斜杠命令绑定草稿：编辑器就绪后加载、整体重载（回滚/时光机）后重新拉取；以显式 `command_bindings` 键独立持久化（空草稿为 null 清空），加载失败时禁止保存以免空草稿覆盖服务端；保存期间的新编辑不被覆盖 |
| `useAgentEditorSave.ts`       | 面板级统一保存编排：命令绑定与其余配置两条互不覆盖的更新对用户只呈现一个保存入口；绑定先存，校验未过或失败即整体中止，只有绑定改动时不触发整体更新；统一提供 `hasChanges`/`saving`/保存并开始对话                              |
| `useAgentGallery.ts`          | 输入框智能体下拉的内置预设与自定义智能体列表、点击切换；挂载时启动尚未就绪的 Provider，并强制刷新一次完整智能体名册（Provider 就绪不再重复拉取）                                                                               |
| `useAgentAiBuild.ts`          | 新建 Agent 页「描述你想要的 Agent」：流式读取草稿并只应用本机存在的技能/MCP/内置工具；失败只给本地化句（缺模型按 `model_not_configured` 单独提示），后端原文只写 console                                                       |
| `useDefaultAgentBootstrap.ts` | 首次进入且无任何配置时选中内置通用智能体（已有配置不覆盖）                                                                                                                                                                     |
| `useAgentResources.ts`        | 资源选择解析                                                                                                                                                                                                                   |
| `useAgentName.ts`             | agent_id → 本地化显示名（内置 agent 走 `getBuiltinAgentName`）                                                                                                                                                                 |
| `useAgentReadiness.ts`        | Per-agent readiness SWR hook (5min polling)                                                                                                                                                                                    |
| `useSkillDiscovery.ts`        | 技能发现、预览、安装、卸载及 `skill_pool_updated` 实时热同步                                                                                                                                                                   |
| `config-panel/`               | 配置变更检测与 save handler                                                                                                                                                                                                    | [_ARCH.md](config-panel/_ARCH.md) |

消费者：`chat-window/agent-config-panel/`、Settings ai-core、kanban。

保存或 AI 创建的文字被服务端风控拦下（HTTP 400 `risk_held`）时，只有 `services/riskHeldToast.ts` 的统一提示；这里的失败提示用 `isRiskHeldError` / `riskHeldErrorFromResponse` 判断后跳过，不另弹「操作失败」。
