# lib/skills/

技能相关纯函数（OAuth 展示名等非 UI 逻辑）。

| 文件                                         | 职责                                                                                                                                                                                                                               |
| -------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `composeLearnSlashMessage.ts`                | Hermes 三字段 → raw `/learn …` 拼接（server SSOT rewrite 输入）                                                                                                                                                                    |
| `submitLearnMessage.ts`                      | 无 chat 时 `initializeChat`+`addPane`，再 `sendMessage`；被拒（返回 false）报告 `refused`，调用方保留用户输入                                                                                                                      |
| `integrationOAuthDisplay.ts`                 | 技能不可用原因展示：OAuth / MCP / xAI 设置链接（缺账号/连接器且未声明 bins / env / config 时走 i18n 文案，同时声明时显示服务端原因，因为缺的可能不是账号），及仅依赖 env 密钥的技能（`skill.requires` 推导）的就地「配置密钥」判定，以及 OAuth 账号的展示名（`formatOAuthIssuerLabel`，`xai` 写作 xAI）；所有 OAuth 账号统一在 Credentials 页管理（`SETTINGS_CREDENTIALS_PATH`） |
| `skillContentSync.ts`                        | 跨表面技能内容刷新广播（chat batch undo → 打开的 Skill 详情 sheet reload）                                                                 |
| `versionOrigin.ts`                           | 技能版本 `created_by`（服务端内部标识）→ 本地化来源名称；未知来源返回 null，界面省略而不展示原始标识                                                                                                                                |
| `scanRiskText.ts`                            | 安全扫描结论与待审原因的本地化出口：风险信号解析、威胁类别/严重度/信号文案与处置建议；类别与严重度以封闭词表判定（词表外显示通用文案，对象原型成员也不会被当成类别），不暴露内部代码        |
| `__tests__/composeLearnSlashMessage.test.ts` | raw `/learn` 拼接纯函数回归                                                                                                                                                                                                        |
| `__tests__/integrationOAuthDisplay.test.ts`  | 多连接器声明路径、env 密钥门控判定与 issuer 落点 / 展示名回归                                                                                                                                                                                            |
| `__tests__/versionOrigin.test.ts`            | 来源标识 → 文案键映射，及未知 / 原型链标识（`constructor`、`__proto__`）不外露回归                                                                                                                                                 |
| `__tests__/scanRiskText.test.ts`             | 六语文案同构、词表与译文键同步、未知/原型链标识不外露、信号占位符与处置建议去重回归                                                                                                         |
