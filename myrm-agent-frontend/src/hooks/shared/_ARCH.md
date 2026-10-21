# hooks/shared/

跨域复用小 hook（无单一业务域归属）。

| 文件                       | 职责                                                                                                                                                                                                                                      |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `useToast.ts`              | toast 封装                                                                                                                                                                                                                                |
| `useDraftPersistence.ts`   | 输入草稿 localStorage                                                                                                                                                                                                                     |
| `useDiffParser.ts`         | unified diff 解析                                                                                                                                                                                                                         |
| `useDeployMode.ts`         | 部署模式检测 wrapper                                                                                                                                                                                                                      |
| `useQuarantineCheck.ts`    | quarantine 文件检查                                                                                                                                                                                                                       |
| `usePendingMemoryToast.ts` | 聊天页挂载时拉取待审批队列建立基线（不提示；首次失败则以首次成功刷新为基线），之后队列增长时 toast 一次                                                                                                                                   |
| `useStoreSnapshot.ts`      | 高频流式热路径手动订阅（DefaultLane 化唤醒 + #185 守卫包装，见 lib/rendering）                                                                                                                                                            |
| `useXaiDeviceLogin.ts`     | xAI 订阅的设备码登录（RFC 8628）：持有轮询节奏（遵循服务端 `interval`，`slow_down` 加 5s，到 `expires_in` 截止）与连接状态，成功后经 `connectProviderSubscription` 写入 provider 状态；聊天横幅、模型页、凭证页共用，各端只负责展示与文案 |
| `useCopyFeedback.ts`       | 经共享剪贴板工具（Tauri/Web 双路径）复制文本并给出 2s「已复制」确认；重复复制重启窗口，卸载后不留定时器                                                                                                                                   |

消费者：message-input、settings、workspace-browser 等。
