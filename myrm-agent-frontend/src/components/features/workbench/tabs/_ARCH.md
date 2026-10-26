# components/features/workbench/tabs/

多标签辅助工作台（`../MultiTabWorkbench.tsx`）的两个面板，都作用于当前会话的工作区（`chatId` 由外壳传入）。数据来自 `@/services/workbench`，选中文件、终端历史等跨面板状态来自 `@/store/useWorkbenchStore`。测试在上级 `../__tests__/`。

| 文件                        | 职责                                                                           |
| --------------------------- | ------------------------------------------------------------------------------ |
| `WorkbenchFileExplorer.tsx` | 会话工作区目录树、快速搜索与文件预览（`fetchWorkspaceFiles`、`fetchFileContent`） |
| `WorkbenchTerminal.tsx`     | 终端面板：命令历史、在会话工作区执行命令（`executeTerminalCommand`）、把输出注入聊天上下文 |
