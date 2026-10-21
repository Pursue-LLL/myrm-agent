# hooks/shell/

应用壳层全局状态（全部署模式 + Tauri tray 消费 liveness）。

| 文件                           | 职责                                                                                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `useLivenessState.ts`          | Agent liveness SSOT（busy/idle/degraded/draining/offline）                                                                                  |
| `useTabBadge.ts`               | document.title 状态前缀                                                                                                                     |
| `useNavBadges.ts`              | NavBar badge（cron/approvals/notifications）                                                                                                |
| `useGlobalShortcuts.ts`        | Cmd+N/B/1-9 等全局快捷键                                                                                                                    |
| `useComputerUseEscapeAbort.ts` | Esc 中止进行中的 Computer Use turn（window capture 阶段）；输入法组合中的 Esc 已被 `app-shell/ime-key-guard-initializer` 先行拦下，不会中止 |
| `useCrashLoopGuard.ts`         | 崩溃循环检测与恢复对话框                                                                                                                    |
| `useIntentMessages.ts`         | 深链/OAuth 回调 toast 与默认档案名的本地化文案（memo 稳定）                                                                                 |

消费者：`AppLayout`、`NavBar`、`LivenessIndicator`、`tauri/useTrayStatus`。
