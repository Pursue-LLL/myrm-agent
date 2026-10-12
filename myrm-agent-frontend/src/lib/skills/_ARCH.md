# lib/skills/

技能相关纯函数（OAuth 展示名等非 UI 逻辑）。

| 文件                                         | 职责                                                                                                                                                                                                                               |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `composeLearnSlashMessage.ts`                | Hermes 三字段 → raw `/learn …` 拼接（server SSOT rewrite 输入）                                                                                                                                                                    |
| `submitLearnMessage.ts`                      | 无 chat 时 `initializeChat`+`addPane`，再 `sendMessage`；被拒（返回 false）报告 `refused`，调用方保留用户输入                                                                                                                      |
| `integrationOAuthDisplay.ts`                 | 技能不可用原因展示：OAuth / MCP / xAI 设置链接（缺账号/连接器且未声明 bins / env / config 时走 i18n 文案，同时声明时显示服务端原因，因为缺的可能不是账号），及仅依赖 env 密钥的技能（`skill.requires` 推导）的就地「配置密钥」判定 |
| `__tests__/composeLearnSlashMessage.test.ts` | raw `/learn` 拼接纯函数回归                                                                                                                                                                                                        |
| `__tests__/integrationOAuthDisplay.test.ts`  | 多连接器声明路径与 env 密钥门控判定回归                                                                                                                                                                                            |
