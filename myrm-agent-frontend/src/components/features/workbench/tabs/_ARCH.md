# components/features/workbench/tabs/

多标签辅助工作台（`../MultiTabWorkbench.tsx`）的四个面板。数据来自 `@/services/workbench`，选中文件等跨面板状态来自 `@/store/useWorkbenchStore`。测试在上级 `../__tests__/`。

| 文件                        | 职责                                                                                         |
| --------------------------- | -------------------------------------------------------------------------------------------- |
| `WorkbenchFileExplorer.tsx` | 工作区目录树、快速搜索与文件预览（`fetchWorkspaceFiles`、`fetchFileContent`）                |
| `WorkbenchDiffViewer.tsx`   | 并排 / 行内代码 Diff，含增删统计与 hunk 标记（`computeFileDiff`）                            |
| `WorkbenchTerminal.tsx`     | 终端面板：命令历史、命令执行（`executeTerminalCommand`）、把输出注入聊天上下文               |
| `WorkbenchPluginCenter.tsx` | 插件列表、健康探测与修复入口（`fetchWorkbenchPlugins`、`probePluginHealth`）                 |
