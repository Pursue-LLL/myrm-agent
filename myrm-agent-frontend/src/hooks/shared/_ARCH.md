# hooks/shared/

跨域复用小 hook（无单一业务域归属）。

| 文件                     | 职责                                                                           |
| ------------------------ | ------------------------------------------------------------------------------ |
| `useToast.ts`            | toast 封装                                                                     |
| `useDraftPersistence.ts` | 输入草稿 localStorage                                                          |
| `useDiffParser.ts`       | unified diff 解析                                                              |
| `useDeployMode.ts`       | 部署模式检测 wrapper                                                           |
| `useTokenCount.ts`       | token 计数                                                                     |
| `useQuarantineCheck.ts`  | quarantine 文件检查                                                            |
| `useStoreSnapshot.ts`    | 高频流式热路径手动订阅（DefaultLane 化唤醒 + #185 守卫包装，见 lib/rendering） |

消费者：message-input、settings、cli-visualization 等。
