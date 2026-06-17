# billing/

## 架构概述

SaaS / Sandbox Work Unit 门禁与配额展示。Entitlement gate 组件拦截未授权能力；`QuotaDisplay` 在账户设置页展示订阅配额。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BudgetExceededDialog.tsx` | 核心 | 预算超限全局弹窗 | ✅ |
| `CronEntitlementGate.tsx` | 核心 | Cron 功能 entitlement 门禁 | ✅ |
| `IngressEntitlementGate.tsx` | 核心 | Ingress 功能 entitlement 门禁 | ✅ |
| `SubagentEntitlementGate.tsx` | 核心 | 子 Agent entitlement 门禁 | ✅ |
| `WorkUnitBalanceBar.tsx` | 核心 | 对话页 Work Unit 余额条 | ✅ |
| `QuotaDisplay.tsx` | 核心 | 账户设置页配额与用量卡片 | ✅ |

## 相关 Hooks（`src/hooks/`）

| Hook | 职责 |
|------|------|
| `useBillingCatalog` | CP 公开定价 catalog SWR |
| `useSessionWuBurnTracker` | 任务结束 WU 消耗 toast（balance delta） |
| `useQuotaGuard` | 发消息前 WU 预估与拦截 |
| `useEntitlements` | CP 权益 + 余额 SWR |

## 依赖

- `@/hooks/useSubscription`、`@/hooks/useEntitlements`
- 父模块 [`components/_ARCH.md`](../_ARCH.md)
