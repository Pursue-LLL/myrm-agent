'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Tick02Icon } from 'hugeicons-react';
import { Button } from '@/components/primitives/button';
import { Switch } from '@/components/primitives/switch';
import { cn } from '@/lib/utils/classnameUtils';
import useAuthStore from '@/store/useAuthStore';
import { isLocalMode, isSandbox } from '@/lib/deploy-mode';
import { useEntitlements } from '@/hooks/useEntitlements';
import { useBillingCatalog } from '@/hooks/useBillingCatalog';
import { mergeBillingCatalog, formatWu, type PaidBillingPlanKey } from '@/lib/billing-plans';
import { toast } from '@/lib/utils/toast';

export default function PricingPage() {
  const t = useTranslations('billing.pricing');
  const router = useRouter();
  const { isAuthenticated, user, token } = useAuthStore();
  const { entitlements } = useEntitlements();
  const { catalog, isLoading: catalogLoading, error: catalogError } = useBillingCatalog();
  const planCatalog = catalog ? mergeBillingCatalog(catalog.plans) : [];
  const [isYearly, setIsYearly] = useState(false);
  const [checkoutLoading, setCheckoutLoading] = useState<PaidBillingPlanKey | null>(null);

  const currentPlan = isSandbox() && entitlements ? entitlements.plan : 'free';
  const billingNotReady =
    isSandbox() &&
    !catalogLoading &&
    planCatalog.some((plan) => plan.key !== 'free' && !plan.checkoutAvailable);

  const PREV_PLAN: Record<string, string | null> = {
    free: null,
    companion: 'Free',
    plus: 'Companion',
    pro: 'Plus',
    max: 'Pro',
  };

  const handleSubscribe = async (planKey: PaidBillingPlanKey, enableTrial: boolean = false) => {
    if (!isAuthenticated) {
      router.push('/auth/login?redirect=/pricing');
      return;
    }

    const planEntry = planCatalog.find((plan) => plan.key === planKey);
    if (!planEntry?.checkoutAvailable) {
      return;
    }

    setCheckoutLoading(planKey);
    try {
      const authToken = token || localStorage.getItem('auth_token');
      const response = await fetch('/api/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          plan: planKey,
          billingCycle: isYearly ? 'yearly' : 'monthly',
          email: user?.email,
          enableTrial,
        }),
      });

      if (!response.ok) {
        toast.error(t('checkoutFailed'));
        return;
      }

      const { checkoutUrl } = (await response.json()) as { checkoutUrl?: string };
      if (!checkoutUrl) {
        toast.error(t('checkoutFailed'));
        return;
      }

      window.location.href = checkoutUrl;
    } catch {
      toast.error(t('checkoutFailed'));
    } finally {
      setCheckoutLoading(null);
    }
  };

  const content = (
    <div className="relative py-16 sm:py-24 px-4 sm:px-6 overflow-hidden">
      {/* Radial gradient ambient glow */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 h-[600px] w-[600px] rounded-full bg-primary/[0.06] blur-[120px]" />
        <div className="absolute bottom-0 right-0 translate-x-1/3 translate-y-1/3 h-[400px] w-[400px] rounded-full bg-primary-dark/[0.08] blur-[100px]" />
        <div className="absolute top-1/2 left-0 -translate-x-1/2 h-[300px] w-[300px] rounded-full bg-primary-hover/[0.05] blur-[80px]" />
      </div>

      {/* Subtle dot grid pattern */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.03] dark:opacity-[0.04]"
        style={{
          backgroundImage: 'radial-gradient(circle, currentColor 1px, transparent 1px)',
          backgroundSize: '24px 24px',
        }}
      />

      <div className="relative mx-auto max-w-6xl">
        {/* Hero Section */}
        <div className="mb-16 sm:mb-20 text-center">
          <h1 className="mb-4 text-4xl font-black tracking-tight sm:text-5xl lg:text-6xl bg-gradient-to-b from-foreground to-foreground/70 bg-clip-text text-transparent">
            {t('title')}
          </h1>
          <p className="text-base text-muted-foreground/80 sm:text-lg max-w-xl mx-auto leading-relaxed">
            {t('subtitle')}
          </p>
          {!isLocalMode() ? (
            <div className="mt-10 inline-flex items-center gap-4 rounded-full border border-border/40 bg-background/60 backdrop-blur-lg px-6 py-3">
              <span
                className={cn(
                  'text-sm transition-all',
                  !isYearly ? 'font-semibold text-foreground' : 'text-muted-foreground/60',
                )}
              >
                {t('monthly')}
              </span>
              <Switch checked={isYearly} onCheckedChange={setIsYearly} />
              <span
                className={cn(
                  'text-sm transition-all',
                  isYearly ? 'font-semibold text-foreground' : 'text-muted-foreground/60',
                )}
              >
                {t('yearly')}
              </span>
            </div>
          ) : null}
          {billingNotReady ? (
            <p className="mt-6 max-w-2xl mx-auto text-center text-sm leading-relaxed text-muted-foreground rounded-xl border border-border/50 bg-muted/20 px-4 py-3">
              {t('checkoutUnavailableBanner')}
            </p>
          ) : null}
        </div>

        {/* Pricing Grid — horizontal snap on mobile, 5-col on xl */}
        <div
          className={cn(
            'flex gap-5 overflow-x-auto snap-x snap-mandatory pb-4 -mx-4 px-4 sm:mx-0 sm:px-0',
            'xl:grid xl:grid-cols-5 xl:overflow-visible xl:snap-none xl:pb-0 items-start',
          )}
        >
          {catalogLoading && planCatalog.length === 0
            ? Array.from({ length: 5 }).map((_, index) => (
                <div
                  key={`pricing-skeleton-${index}`}
                  className="min-w-[min(100%,280px)] snap-center shrink-0 xl:min-w-0 rounded-2xl border border-border/40 bg-muted/20 p-6 h-[420px] animate-pulse"
                />
              ))
            : null}
          {!catalogLoading || planCatalog.length > 0
            ? planCatalog.map(
            ({ key, icon: Icon, monthlyUsd, yearlyUsd, monthlyWu, highlight, trialDays, checkoutAvailable }) => {
            const isCurrent = currentPlan === key;
            const isPaid = key !== 'free';
            const displayPrice = isYearly && isPaid ? yearlyUsd : monthlyUsd;
            const hasTrial = trialDays > 0 && currentPlan === 'free';

            return (
              <div
                key={key}
                className={cn(
                  'group relative flex flex-col rounded-2xl p-[1px] transition-all duration-500 min-w-[min(100%,280px)] snap-center shrink-0',
                  'xl:min-w-0 xl:shrink',
                  highlight
                    ? 'bg-gradient-to-b from-primary/60 via-primary/30 to-primary-dark/20 scale-[1.02] xl:-mt-4 xl:mb-4 shadow-2xl shadow-primary/10'
                    : 'bg-border/50 hover:bg-border/80',
                )}
              >
                {/* Inner card */}
                <div
                  className={cn(
                    'relative flex flex-col flex-1 rounded-[15px] p-6 sm:p-7 transition-all duration-300',
                    highlight ? 'bg-background' : 'bg-background/95 backdrop-blur-sm group-hover:bg-background',
                  )}
                >
                  {/* Highlight glow */}
                  {highlight && (
                    <div className="absolute -top-px left-1/2 -translate-x-1/2 h-[2px] w-3/4 bg-gradient-to-r from-transparent via-primary/80 to-transparent" />
                  )}

                  {/* Trial badge */}
                  {hasTrial && (
                    <div className="absolute -top-3 right-5 rounded-full bg-gradient-to-r from-primary to-primary-hover px-3.5 py-1 text-[11px] font-bold text-primary-foreground shadow-lg shadow-primary/25 tracking-wide uppercase">
                      {t('trialBadge')}
                    </div>
                  )}

                  {/* Header */}
                  <div className="mb-6">
                    <div className="flex items-center gap-3 mb-2">
                      <div
                        className={cn(
                          'rounded-xl p-2 transition-colors',
                          highlight ? 'bg-primary/10' : 'bg-muted/50 dark:bg-white/[0.04]',
                        )}
                      >
                        <Icon size={18} className={cn(highlight ? 'text-primary' : 'text-muted-foreground')} />
                      </div>
                      <h3 className="text-base font-bold tracking-tight">{t(`plans.${key}.name`)}</h3>
                    </div>
                    <p className="text-[13px] text-muted-foreground/70 leading-relaxed">
                      {t(`plans.${key}.description`)}
                    </p>
                  </div>

                  {/* Price */}
                  <div className="mb-6">
                    <div className="flex items-baseline gap-1.5">
                      {isYearly && isPaid && (
                        <span className="text-lg text-muted-foreground/40 line-through font-medium">${monthlyUsd}</span>
                      )}
                      <span
                        className={cn(
                          'text-[42px] font-black tracking-tighter leading-none',
                          highlight
                            ? 'bg-gradient-to-br from-foreground via-foreground to-foreground/60 bg-clip-text text-transparent'
                            : '',
                        )}
                      >
                        ${isYearly && isPaid ? Math.round(yearlyUsd / 12) : displayPrice}
                      </span>
                      <span className="text-sm text-muted-foreground/60 font-medium">{t('perMonth')}</span>
                    </div>
                    {isYearly && isPaid ? (
                      <p className="mt-1.5 text-xs text-muted-foreground/50">
                        {t('yearlyEquivalent', { amount: `$${yearlyUsd}` })}
                      </p>
                    ) : (
                      <div className="mt-1.5 h-4" />
                    )}
                  </div>

                  {/* WU allocation */}
                  <div
                    className={cn(
                      'mb-6 rounded-lg px-3 py-2',
                      highlight ? 'bg-primary/[0.06] dark:bg-primary/[0.08]' : 'bg-muted/40 dark:bg-white/[0.03]',
                    )}
                  >
                    <p className="text-sm font-bold text-foreground/90">
                      {t('wuPerMonth', { wu: formatWu(monthlyWu) })}
                    </p>
                  </div>

                  {/* Feature list */}
                  <ul className="space-y-3 text-[13px] text-muted-foreground/80 mb-8 flex-1">
                    {PREV_PLAN[key] ? (
                      <li className="text-[11px] font-semibold text-muted-foreground/50 tracking-wider mb-1">
                        {t('everythingIn', { plan: PREV_PLAN[key] })}
                      </li>
                    ) : (
                      <li className="text-[11px] font-semibold text-muted-foreground/50 tracking-wider mb-1">
                        {t('including')}
                      </li>
                    )}
                    <li className="flex items-start gap-2.5">
                      <Tick02Icon
                        size={14}
                        className={cn('shrink-0 mt-0.5', highlight ? 'text-primary' : 'text-muted-foreground/50')}
                      />
                      <span>{t(`plans.${key}.feature1`)}</span>
                    </li>
                    <li className="flex items-start gap-2.5">
                      <Tick02Icon
                        size={14}
                        className={cn('shrink-0 mt-0.5', highlight ? 'text-primary' : 'text-muted-foreground/50')}
                      />
                      <span>{t(`plans.${key}.feature2`)}</span>
                    </li>
                  </ul>

                  {/* CTA */}
                  <div className="flex flex-col gap-2 mt-auto">
                    {hasTrial && (
                      <Button
                        className={cn(
                          'w-full font-semibold rounded-full',
                          highlight &&
                            'bg-gradient-to-r from-primary to-primary-hover hover:opacity-90 shadow-lg shadow-primary/20 border-0',
                        )}
                        variant="default"
                        disabled={checkoutLoading !== null || !checkoutAvailable}
                        onClick={() => handleSubscribe(key as PaidBillingPlanKey, true)}
                      >
                        {checkoutLoading === key
                          ? t('processing')
                          : !checkoutAvailable
                            ? t('checkoutUnavailable')
                            : t('startTrial')}
                      </Button>
                    )}
                    <Button
                      className={cn(
                        'w-full rounded-full',
                        highlight &&
                          !hasTrial &&
                          'bg-gradient-to-r from-primary to-primary-hover hover:opacity-90 shadow-lg shadow-primary/20 border-0 font-semibold',
                      )}
                      variant={highlight && !hasTrial ? 'default' : 'outline'}
                      disabled={isCurrent || (isPaid && checkoutLoading !== null) || !isPaid || !checkoutAvailable}
                      onClick={() => (isPaid ? handleSubscribe(key as PaidBillingPlanKey) : undefined)}
                    >
                      {checkoutLoading === key && !hasTrial
                        ? t('processing')
                        : isCurrent
                          ? t('currentPlan')
                          : isPaid && !checkoutAvailable
                            ? t('checkoutUnavailable')
                            : isPaid
                              ? t('subscribe')
                              : t('included')}
                    </Button>
                  </div>
                </div>
              </div>
            );
          })
            : null}
        </div>
        {catalogError ? (
          <p className="mt-6 text-center text-sm text-destructive">{t('catalogLoadFailed')}</p>
        ) : null}
      </div>
    </div>
  );

  return content;
}
