/**
 * [INPUT]
 * - myrm_control_plane/billing/plans.py::PLAN_ENTITLEMENTS (POS: 各 tier 权益表)
 *
 * [OUTPUT]
 * - BILLING_PLAN_CATALOG: SaaS 定价页展示用静态 catalog（WU 配额与 CP 一致）
 * - formatWu: WU 数字格式化
 *
 * [POS]
 * 前端计费展示常量层。Stripe 价格由 Dashboard 配置，此处仅维护展示用 USD 与 WU 配额。
 */

import type { ComponentType } from 'react';
import { AiMagicIcon, CloudIcon, Rocket01Icon, Layers01Icon } from 'hugeicons-react';

export type BillingPlanKey = 'free' | 'companion' | 'pro' | 'max';
export type PaidBillingPlanKey = Exclude<BillingPlanKey, 'free'>;

export interface BillingPlanCatalogEntry {
  key: BillingPlanKey;
  icon: ComponentType<{ size?: number; className?: string }>;
  monthlyUsd: number;
  yearlyUsd: number;
  monthlyWu: number;
  highlight: boolean;
  trialDays: number;
}

/** WU quotas must match CP `PLAN_ENTITLEMENTS` monthly_wu values. */
export const BILLING_PLAN_CATALOG: BillingPlanCatalogEntry[] = [
  { key: 'free', icon: AiMagicIcon, monthlyUsd: 0, yearlyUsd: 0, monthlyWu: 600, highlight: false, trialDays: 0 },
  {
    key: 'companion',
    icon: CloudIcon,
    monthlyUsd: 19,
    yearlyUsd: 190,
    monthlyWu: 6000,
    highlight: false,
    trialDays: 0,
  },
  { key: 'pro', icon: Rocket01Icon, monthlyUsd: 49, yearlyUsd: 490, monthlyWu: 18000, highlight: true, trialDays: 7 },
  {
    key: 'max',
    icon: Layers01Icon,
    monthlyUsd: 149,
    yearlyUsd: 1490,
    monthlyWu: 60000,
    highlight: false,
    trialDays: 0,
  },
];

export const TOPUP_WU_PER_USD = 1000;

export function formatWu(value: number): string {
  return value.toLocaleString();
}
