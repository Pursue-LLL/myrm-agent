# hooks/shell/

应用壳层全局状态（全部署模式 + Tauri tray 消费 liveness）。

| 文件 | 职责 |
|------|------|
| `useLivenessState.ts` | Agent liveness SSOT（busy/idle/degraded/draining/offline） |
| `useTabBadge.ts` | document.title 状态前缀 |
| `useNavBadges.ts` | NavBar badge（cron/approvals/notifications） |
| `useGlobalShortcuts.ts` | Cmd+N/B/1-9 等全局快捷键 |
| `useCrashLoopGuard.ts` | 崩溃循环检测与恢复对话框 |

消费者：`AppLayout`、`NavBar`、`LivenessIndicator`、`tauri/useTrayStatus`。
