# lib/skills/

技能相关纯函数（OAuth 展示名等非 UI 逻辑）。

| 文件                                         | 职责                                                                                                                   |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `composeLearnSlashMessage.ts`                | Hermes 三字段 → raw `/learn …` 拼接（server SSOT rewrite 输入）                                                        |
| `submitLearnMessage.ts`                      | 无 chat 时 `initializeChat`+`addPane`，再 `sendMessage`                                                                |
| `integrationOAuthDisplay.ts`                 | 技能不可用原因展示：OAuth / MCP / xAI 设置链接（缺账号/连接器统一走 i18n 文案，不直出服务端英文原因），及仅依赖 env 密钥的技能（`skill.requires` 推导）的就地「配置密钥」判定 |
| `__tests__/composeLearnSlashMessage.test.ts` | raw `/learn` 拼接纯函数回归                                                                                            |
| `__tests__/integrationOAuthDisplay.test.ts`  | 多连接器声明路径与 env 密钥门控判定回归                                                                                |
