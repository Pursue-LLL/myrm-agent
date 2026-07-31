# lib/skills/

技能相关纯函数（OAuth 展示名等非 UI 逻辑）。

| 文件 | 职责 |
|------|------|
| `composeLearnSlashMessage.ts` | Hermes 三字段 → raw `/learn …` 拼接（server SSOT rewrite 输入） |
| `submitLearnMessage.ts` | 无 chat 时 `initializeChat`+`addPane`，再 `sendMessage` |
| `integrationOAuthDisplay.ts` | 集成 OAuth provider 展示名解析 |
| `__tests__/composeLearnSlashMessage.test.ts` | raw `/learn` 拼接纯函数回归 |
