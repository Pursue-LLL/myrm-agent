# hooks/copilot/

| 文件              | 职责                                                                                  | I/O/P |
| ----------------- | ------------------------------------------------------------------------------------- | ----- |
| `useRunDigest.ts` | 按 chatId 拉取 run digest；订阅 `run-digest-updated` 与 `app_resync_required` refetch | ✅    |
