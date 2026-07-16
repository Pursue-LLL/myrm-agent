/**
 * [INPUT]
 * - CP GET /api/billing/catalog (POS: USD + WU SSOT)
 *
 * [OUTPUT]
 * - BILLING_PLAN_PRESENTATION: 前端展示元数据（icon/highlight）
 * - mergeBillingCatalog: 合并 CP catalog 与展示元数据
 * - formatWu: WU 数字格式化
 *
 * [POS]
 * 定价页展示层。USD/WU 数字来自 CP catalog，此处仅保留 UI 元数据。
 */

import type { ComponentType } from 'react';
import { AiMagicIcon, CloudIcon, Diamond02Icon, Rocket01Icon, Layers01Icon } from 'hugeicons-react';
import type { BillingCatalogPlan, BillingPlanKey } from '@/lib/cp-billing';

export type { BillingPlanKey, PaidBillingPlanKey } from '@/lib/cp-billing';

export interface BillingPlanCatalogEntry {
  key: BillingPlanKey;
  icon: ComponentType<{ size?: number; className?: string }>;
  monthlyUsd: number;
  yearlyUsd: number;
  monthlyWu: number;
  highlight: boolean;
  trialDays: number;
  checkoutAvailable: boolean;
}

const PRESENTATION: Record<
  BillingPlanKey,
  { icon: ComponentType<{ size?: number; className?: string }>; highlight: boolean }
> = {
  free: { icon: AiMagicIcon, highlight: false },
  companion: { icon: CloudIcon, highlight: false },
  plus: { icon: Diamond02Icon, highlight: false },
  pro: { icon: Rocket01Icon, highlight: true },
  max: { icon: Layers01Icon, highlight: false },
};

const PLAN_ORDER: BillingPlanKey[] = ['free', 'companion', 'plus', 'pro', 'max'];

export function mergeBillingCatalog(plans: BillingCatalogPlan[]): BillingPlanCatalogEntry[] {
  const byKey = new Map(plans.map((p) => [p.plan, p]));
  return PLAN_ORDER.map((key) => {
    const remote = byKey.get(key);
    const meta = PRESENTATION[key];
    return {
      key,
      icon: meta.icon,
      highlight: meta.highlight,
      monthlyUsd: remote?.monthly_usd ?? 0,
      yearlyUsd: remote?.yearly_usd ?? 0,
      monthlyWu: remote?.monthly_wu ?? 0,
      trialDays: remote?.trial_days ?? 0,
      checkoutAvailable: remote?.checkout_available ?? false,
    };
  });
}

export function formatWu(value: number): string {
  return value.toLocaleString();
}
