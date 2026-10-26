# components/features/workbench/tabs/

多标签辅助工作台（`../MultiTabWorkbench.tsx`）的两个面板，都作用于当前会话的工作区：文件页从 `useChatStore.workspaceDir` 取工作区目录，终端的 `chatId` 由外壳传入。文件页的数据来自 `workspace-browser`，终端的命令执行来自 `@/services/workbench`，终端历史来自 `@/store/useWorkbenchStore`。测试在上级 `../__tests__/`。

| 文件                        | 职责                                                                           |
| --------------------------- | ------------------------------------------------------------------------------ |
| `WorkbenchFiles.tsx`        | 会话工作区文件页：搜索框（`filterFileEntries`）+ 复用 `workspace-browser` 的目录树（`useWorkspaceFiles`）与文件预览 |
| `WorkbenchTerminal.tsx`     | 终端面板：命令历史、在会话工作区执行命令（`executeTerminalCommand`）、把输出注入聊天上下文 |
