# agent/config-panel/

`useAgentConfigPanel.ts` 的逻辑切片：将面板动作和配置变更检测从主 hook 拆出以控制行数。

| 文件               | 职责                                                                                                                                                          |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `handlers.ts`      | 保存/重置/技能绑定等 imperative handlers；保存时指令内容真的变了才置 `systemPromptEdited`（仅此时 `agent_config.system_prompt` 随请求发送），原样保存不算改写 |
| `configChanges.ts` | 配置变更检测纯函数 + `OriginalAgentSnapshot`；`normalizeSkillConfigs` / `areSkillConfigsEqual` 含 instance 绑定                                               |

主 hook 在同级 `../useAgentConfigPanel.ts`。
