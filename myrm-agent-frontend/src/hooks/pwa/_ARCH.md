# hooks/pwa/

PWA 与版本感知。

| 文件                     | 职责                            |
| ------------------------ | ------------------------------- |
| `usePWAInstall.ts`       | beforeinstallprompt 安装引导    |
| `usePushSubscription.ts` | Web Push VAPID 订阅             |
| `useWhatsNew.ts`         | 版本变更 → GitHub Release Notes |

消费者：`app-shell/`、Settings Personal/System。
