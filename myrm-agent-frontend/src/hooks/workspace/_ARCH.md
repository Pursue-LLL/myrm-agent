# hooks/workspace/

工作区与 artifact 相关流式/存储 hook。

| 文件                                    | 职责                                                                                                                                                                                                         |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `useWorkspaceStream.ts`                 | 工作区事件流（`/workspace/stream`）的连接生命周期：登录后连接、登出断开；非生产构建里 E2E 绑定落定（`myrm_e2e_runtime_ready`）时与绑定存续期间（1.5 s 轮询）重连，让流跟到私有后端，生产构建既不监听也不轮询 |
| `useWidgetStorage.ts`                   | Widget iframe localStorage 桥接                                                                                                                                                                              |
| `useArtifactVersionsFromHistory.ts`     | 从历史解析 artifact 版本                                                                                                                                                                                     |
| `__tests__/useWorkspaceStream.test.tsx` | 钉住连接生命周期：登录连接、登出断开；开发构建里绑定事件与 1.5 s 轮询触发重连；生产构建零监听、零定时器                                                                                                      |

消费者：`project-workspace/`、artifacts、workspace-browser。
