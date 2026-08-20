# hooks/billing/

SaaS 配额、订阅、ingress 与用量。

| 文件                                               | 职责                     |
| -------------------------------------------------- | ------------------------ |
| `useSubscription.ts`                               | 订阅状态                 |
| `useEntitlements.ts` / `useFeatureEntitlements.ts` | 功能 entitlements        |
| `useQuotaGuard.ts`                                 | 发送前配额守卫           |
| `useBillingCatalog.ts`                             | CP 定价 catalog          |
| `useWuBalanceWatcher.ts`                           | WU 低余额 → UpgradeNudge |
| `useUsageAnalytics.ts`                             | 用量分析                 |
| `useIngressRequirement.ts` / `useIngressUrl.ts`    | Ingress 要求与 URL       |

消费者：`components/billing/`、Settings channels、NavBar。
