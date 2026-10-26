# components/features/workbench/tabs/

多标签辅助工作台（`../MultiTabWorkbench.tsx`）的两个面板，都作用于当前会话的工作区：文件页从 `useChatStore.workspaceDir` 取工作区目录，终端的 `chatId` 由外壳传入。文件页的数据来自 `workspace-browser`，终端的命令执行来自 `@/services/workbench`，终端历史来自 `@/store/useWorkbenchStore`。外壳切到终端页签时只隐藏文件页、不卸载它，终端页签按需挂载。测试在上级 `../__tests__/`。

| 文件                        | 职责                                                                                                                                                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `WorkbenchFiles.tsx`        | 会话工作区文件页：复用 `workspace-browser` 的目录树（`useWorkspaceFiles`）与文件预览；搜索框输入后在目录树上盖一层服务端文件名搜索结果，点击结果直接预览；预览有未保存编辑时向抽屉登记关闭确认（`closeGuard`） |
| `useWorkspaceFileSearch.ts` | 文件页搜索 Hook：防抖后调用 `searchWorkspaceFiles` 搜整个工作区（不受目录树已加载层数限制），只采纳最新一次查询的结果，新查询进行时暂留上一批结果                                                              |
| `WorkbenchTerminal.tsx`     | 终端面板：命令历史、在会话工作区执行命令（`executeTerminalCommand`，静默请求）、把输出追加到聊天输入框、请求失败以用户语言入史                                                                                 |
| `terminalOutput.ts`         | 终端纯函数：`buildTerminalSnippet`（围栏随内容自适应、只留输出末尾）、`appendToComposer`、`classifyTerminalFailure`（按 HTTP 状态与超时错误分类）                                                              |
