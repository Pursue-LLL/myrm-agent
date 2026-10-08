# hooks/shared/

跨域复用小 hook（无单一业务域归属）。

| 文件                       | 职责                                                                                                    |
| -------------------------- | ------------------------------------------------------------------------------------------------------- |
| `useToast.ts`              | toast 封装                                                                                              |
| `useDraftPersistence.ts`   | 输入草稿 localStorage                                                                                   |
| `useDiffParser.ts`         | unified diff 解析                                                                                       |
| `useDeployMode.ts`         | 部署模式检测 wrapper                                                                                    |
| `useQuarantineCheck.ts`    | quarantine 文件检查                                                                                     |
| `usePendingMemoryToast.ts` | 聊天页挂载时拉取待审批队列建立基线（不提示；首次失败则以首次成功刷新为基线），之后队列增长时 toast 一次 |
| `useStoreSnapshot.ts`      | 高频流式热路径手动订阅（DefaultLane 化唤醒 + #185 守卫包装，见 lib/rendering）                          |

消费者：message-input、settings、workspace-browser 等。
