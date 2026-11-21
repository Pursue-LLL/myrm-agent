# lib/constants/

前端跨模块共用的常量（路径、官方品牌地址、artifact 类型、代码块主题、聊天历史查询、压缩聚焦主题与顾问提问的长度上限）。

| 文件                                | 职责                                                                                                                                                                                                                                              |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `paths.ts`                          | 应用路由与 API 路径常量                                                                                                                                                                                                                           |
| `brand.ts`                          | 官方品牌地址的定义处：官网根 `OFFICIAL_SITE_URL`、下载页 `OFFICIAL_DOWNLOAD_URL`、文档站根 `OFFICIAL_DOCS_URL`（带 `/docs` 前缀的规范形态）；占位与示例主机用保留域名（`example.com` 系），不取这里的值，免得拼出看似官方、实际不存在的链接       |
| `artifact.ts`                       | 工件 MIME/类型枚举                                                                                                                                                                                                                                |
| `codeblock-theme.ts`                | 代码块的底色与文字色、行号色，以及单行代码芯片 `INLINE_CODE_CHIP`（聊天行内代码与交付物引用链接共用，底色与代码块一致，文字色在两个底色上不低于 4.5:1）                                                                                           |
| `chat-history-search.ts`            | 聊天历史查询的长度上限 `HISTORY_SEARCH_MAX_LENGTH`（读前后端共享的 `chat_input_limits.json`，服务端契约测试保证它等于服务端上限）；侧栏、Cmd+K、共享上下文历史搜索的输入框各自限长，`@chat:` 选择器截断发出的查询                                 |
| `compact-focus-topic.ts`            | 压缩上下文时聚焦主题的长度上限 `COMPACT_FOCUS_TOPIC_MAX_LENGTH`（读同一份 `chat_input_limits.json`，服务端契约测试保证它等于服务端上限）；压缩面板的输入框限长，`compactChat` 发出前按它截断，所以输入 `/compact <主题>` 的路径也不会被服务端拒收 |
| `advisor-question.ts`               | 向会话顾问提问的长度上限 `ADVISOR_QUESTION_MAX_LENGTH`（读同一份 `chat_input_limits.json`，服务端契约测试保证它等于服务端上限）；顾问面板的输入框限长，`askAdvisor` 发出前按它截断，所以 `/ask <问题>` 这类由程序带入问题的路径也不会被服务端拒收 |
| `__tests__/codeblock-theme.test.ts` | 芯片的底色与代码块的底色一致；浅色、深色下文字对比度不低于 4.5:1（色阶从 Tailwind 的 `theme.css` 读，换成更浅的色阶就失败）                                                                                                                       |
