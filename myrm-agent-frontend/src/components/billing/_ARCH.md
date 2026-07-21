# billing/

## 架构概述

SaaS / Sandbox Work Unit 门禁与配额展示。Entitlement gate 组件拦截未授权能力；`QuotaDisplay` 在账户设置页展示订阅配额。计费经 Creem MoR（CP `/api/billing/*`），前端 locale 使用 `billingMoR` 键；`/pricing` 在 `checkout_available=false` 时展示 banner + 禁用 CTA，并在 `handleSubscribe` 内二次校验 `checkoutAvailable`。Entitlements 使用 CP 字段 `billing_customer_id`（`cp-billing.ts`）。Top-up 仅付费订阅用户可见（CP 403 + FE `isPaidPlan` gate）；WU 耗尽时 `BudgetExceededDialog` 引导付费用户充值或升级。

**升级引导双层体系**：
- **事前预防**：`UpgradeNudgeDialog` — 余额 ≤20% 时主动提醒（每 24h 最多 1 次），并在 Feature Gate 点击升级时弹出推荐方案
- **事后补救**：`BudgetExceededDialog` — WU=0 时阻断操作并引导充值或升级

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `BudgetExceededDialog.tsx` | 核心 | 预算超限全局弹窗（WU=0 阻断） | ✅ |
| `UpgradeNudgeDialog.tsx` | 核心 | 升级引导弹窗（低余额预警 + Feature Gate 推荐） | ✅ |
| `CronEntitlementGate.tsx` | 核心 | Cron 功能 entitlement 门禁（触发 NudgeDialog） | ✅ |
| `IngressEntitlementGate.tsx` | 核心 | Ingress 功能 entitlement 门禁（触发 NudgeDialog） | ✅ |
| `WorkUnitBalanceBar.tsx` | 核心 | 对话页 Work Unit 总余额条 | ✅ |
| `SessionSpendSurface.tsx` | 核心 | 对话页 per-turn/session WU 消耗 pill（Sandbox: WU / Local: $） | ✅ |
| `QuotaDisplay.tsx` | 核心 | 账户设置页配额与用量卡片 | ✅ |

## 相关 Hooks（`src/hooks/`）

| Hook | 职责 |
|------|------|
| `useBillingCatalog` | CP 公开定价 catalog SWR |
| `useQuotaGuard` | 发消息前 WU 预估与拦截 |
| `useEntitlements` | CP 权益 + 余额 SWR |
| `useWuBalanceWatcher` | 全局 WU 低余额监听，触发 NudgeDialog |

## 相关 Store（`src/store/`）

| Store | 职责 |
|------|------|
| `useBudgetExceededStore` | BudgetExceededDialog 状态（open/close） |
| `useUpgradeNudgeStore` | UpgradeNudgeDialog 状态 + 24h 防骚扰 |

## 依赖

- `@/hooks/useSubscription`、`@/hooks/useEntitlements`
- `@/lib/cp-billing` — `BillingCatalogPlan.features` 字段由 CP 自动生成
- 父模块 [`components/_ARCH.md`](../_ARCH.md)
