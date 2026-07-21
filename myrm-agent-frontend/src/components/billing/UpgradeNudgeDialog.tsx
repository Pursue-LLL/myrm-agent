'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { useUpgradeNudgeStore } from '@/store/useUpgradeNudgeStore';
import { useSubscription } from '@/hooks/useSubscription';
import { useBillingCatalog } from '@/hooks/useBillingCatalog';
import { useEntitlements } from '@/hooks/useEntitlements';
import { isSandbox } from '@/lib/deploy-mode';
import { type BillingCatalogPlan, type BillingPlanKey } from '@/lib/cp-billing';

const PLAN_ORDER: readonly BillingPlanKey[] = ['free', 'companion', 'plus', 'pro', 'max'];

function getNextPlan(currentPlan: BillingPlanKey | 'team'): BillingPlanKey | null {
  if (currentPlan === 'team') return null;
  const idx = PLAN_ORDER.indexOf(currentPlan);
  if (idx < 0 || idx >= PLAN_ORDER.length - 1) return null;
  return PLAN_ORDER[idx + 1];
}

function findPlanCatalog(
  plans: BillingCatalogPlan[] | undefined,
  target: BillingPlanKey,
): BillingCatalogPlan | undefined {
  return plans?.find((p) => p.plan === target);
}

export default function UpgradeNudgeDialog() {
  const t = useTranslations('billing.nudge');
  const { open, trigger, blockedFeature, close } = useUpgradeNudgeStore();
  const { subscription } = useSubscription();
  const { catalog } = useBillingCatalog();
  const { entitlements } = useEntitlements();

  if (!isSandbox()) return null;

  const currentPlan = subscription.plan_type as BillingPlanKey | 'team';
  const nextPlanKey = getNextPlan(currentPlan);
  const nextPlanCatalog = nextPlanKey ? findPlanCatalog(catalog?.plans, nextPlanKey) : undefined;

  const balanceWu = entitlements?.balance_wu ?? 0;
  const monthlyWu = entitlements?.monthly_allowance_wu ?? 1;
  const pct = Math.round((balanceWu / monthlyWu) * 100);

  const title = trigger === 'low_balance' ? t('lowBalanceTitle') : t('featureGateTitle');

  const description =
    trigger === 'low_balance'
      ? t('lowBalanceDescription', { pct, balance: balanceWu })
      : t('featureGateDescription', { feature: blockedFeature ?? '' });

  return (
    <AlertDialog open={open} onOpenChange={(next) => (!next ? close() : undefined)}>
      <AlertDialogContent className="max-w-md">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{description}</AlertDialogDescription>
        </AlertDialogHeader>

        {nextPlanCatalog && (
          <div className="rounded-xl border border-border/60 bg-muted/30 px-4 py-3 space-y-2">
            <p className="text-sm font-semibold text-foreground">
              {t('recommendPlan', { plan: nextPlanKey!.charAt(0).toUpperCase() + nextPlanKey!.slice(1) })}
            </p>
            <p className="text-xs text-muted-foreground">
              {t('planWu', { wu: nextPlanCatalog.monthly_wu.toLocaleString() })}
              {nextPlanCatalog.monthly_usd > 0 && ` · $${nextPlanCatalog.monthly_usd}/mo`}
            </p>
            {nextPlanCatalog.features.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {nextPlanCatalog.features.map((f) => (
                  <li key={f} className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <span className="text-emerald-500">✓</span>
                    {t(`features.${f}` as Parameters<typeof t>[0], { defaultValue: f })}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel>{t('dismiss')}</AlertDialogCancel>
          <AlertDialogAction asChild>
            <Link href="/pricing" onClick={close}>
              {t('viewPlans')}
            </Link>
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
