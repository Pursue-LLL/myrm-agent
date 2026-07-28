# hooks/shared/

跨域复用小 hook（无单一业务域归属）。

| 文件 | 职责 |
|------|------|
| `useToast.ts` | toast 封装 |
| `useDraftPersistence.ts` | 输入草稿 localStorage |
| `useDiffParser.ts` | unified diff 解析 |
| `useDeployMode.ts` | 部署模式检测 wrapper |
| `useTokenCount.ts` | token 计数 |
| `useQuarantineCheck.ts` | quarantine 文件检查 |

消费者：message-input、settings、cli-visualization 等。
