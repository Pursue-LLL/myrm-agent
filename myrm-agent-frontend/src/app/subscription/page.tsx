'use client';

import { useMemo, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import {
  IconAlertTriangle,
  IconCalendar,
  IconClock,
  IconCreditCard,
  IconGlow,
  IconShieldCheck,
  IconShieldAlert,
  IconCrown,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import useAuthStore from '@/store/useAuthStore';
import LoginPrompt from '@/components/features/app-shell/login-prompt';
import { isLocalMode, isSandbox } from '@/lib/deploy-mode';
import { mergeBillingCatalog, type BillingPlanKey } from '@/lib/billing-plans';
import { useBillingCatalog } from '@/hooks/useBillingCatalog';
import { type SubscriptionStatus, useSubscription } from '@/hooks/useSubscription';
import { toast } from '@/lib/utils/toast';

interface StatusMeta {
  badge: string;
  tone: string;
  icon: React.ComponentType<{ className?: string }>;
}

const STATUS_META: Record<SubscriptionStatus['status'], StatusMeta> = {
  active: {
    badge: 'bg-emerald-500/10 border-emerald-500/20',
    tone: 'text-emerald-500',
    icon: IconShieldCheck,
  },
  trialing: {
    badge: 'bg-blue-500/10 border-blue-500/20',
    tone: 'text-blue-500',
    icon: IconGlow,
  },
  cancelled: {
    badge: 'bg-amber-500/10 border-amber-500/20',
    tone: 'text-amber-500',
    icon: IconAlertTriangle,
  },
  past_due: {
    badge: 'bg-rose-500/10 border-rose-500/20',
    tone: 'text-rose-500',
    icon: IconAlertTriangle,
  },
  expired: {
    badge: 'bg-slate-500/10 border-slate-500/20',
    tone: 'text-slate-400',
    icon: IconShieldAlert,
  },
};

const STATUS_LABEL_KEYS: Record<SubscriptionStatus['status'], string> = {
  active: 'active',
  trialing: 'trialing',
  cancelled: 'cancelled',
  past_due: 'pastDue',
  expired: 'expired',
};

const formatDate = (value: string | null, locale: string, fallback: string) => {
  if (!value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return fallback;
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
};

export default function SubscriptionPage() {
  const t = useTranslations('subscriptionPage');
  const tPricing = useTranslations('pricing');
  const tSubscription = useTranslations('pricing.subscription');
  const tBilling = useTranslations('billing.pricing');
  const locale = useLocale();
  const router = useRouter();
  const { subscription, isLoading, error, refresh, isPaidPlan } = useSubscription();
  const { catalog } = useBillingCatalog();
  const topupWuPerUsd = catalog?.topup_wu_per_usd ?? 1000;
  const planCatalog = catalog ? mergeBillingCatalog(catalog.plans) : [];
  const { user, isInitialized } = useAuthStore();
  const isLocal = isLocalMode();
  const sandbox = isSandbox();
  const [topupLoading, setTopupLoading] = useState(false);

  const handleTopup = async (amountUsd: number) => {
    setTopupLoading(true);
    try {
      const authToken = localStorage.getItem('auth_token');
      const response = await fetch('/api/topup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({ amount_usd: amountUsd }),
      });
      if (!response.ok) {
        toast.error(tBilling('checkoutFailed'));
        return;
      }
      const data = (await response.json()) as { checkoutUrl?: string };
      if (data.checkoutUrl) {
        window.location.href = data.checkoutUrl;
      }
    } catch {
      toast.error(tBilling('checkoutFailed'));
    } finally {
      setTopupLoading(false);
    }
  };

  const statusKey = STATUS_LABEL_KEYS[subscription.status];
  const statusMeta = STATUS_META[subscription.status];
  const StatusIcon = statusMeta.icon;
  const isHealthy = subscription.status === 'active';
  const canOpenPortal =
    Boolean(subscription.billing_customer_id) || (sandbox && isPaidPlan);
  const isEmptyState = !isLoading && !error && subscription.plan_type === 'free' && !subscription.current_period_end;

  const planKeys = planCatalog.map((plan) => plan.key);
  const planName = useMemo(() => {
    if (sandbox && (planKeys as readonly string[]).includes(subscription.plan_type)) {
      return tBilling(`plans.${subscription.plan_type as BillingPlanKey}.name`);
    }
    if (subscription.plan_type === 'free' || subscription.plan_type === 'pro') {
      return tPricing(`${subscription.plan_type}.name`);
    }
    return subscription.plan_type;
  }, [subscription.plan_type, sandbox, tBilling, tPricing]);

  const planDescription = useMemo(() => {
    if (sandbox && (planKeys as readonly string[]).includes(subscription.plan_type)) {
      return tBilling(`plans.${subscription.plan_type as BillingPlanKey}.description`);
    }
    if (subscription.plan_type === 'free' || subscription.plan_type === 'pro') {
      return tPricing(`${subscription.plan_type}.description`);
    }
    return '';
  }, [subscription.plan_type, sandbox, tBilling, tPricing]);

  const ambientBackground = (
    <>
      <div className="absolute -top-24 right-[-120px] h-64 w-64 rounded-full bg-primary/10 blur-3xl" />
      <div className="absolute top-40 left-[-80px] h-48 w-48 rounded-full bg-secondary/20 blur-3xl" />
    </>
  );

  const headerSection = (
    <header className="relative space-y-3">
      <div className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-background/70 px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
        <IconGlow className="w-3.5 h-3.5" />
        {t('overviewTitle')}
      </div>
      <h1 className="text-3xl md:text-4xl font-black text-foreground">{t('title')}</h1>
      <p className="text-sm md:text-base text-muted-foreground max-w-2xl">{t('subtitle')}</p>
    </header>
  );

  const periodStart = formatDate(subscription.current_period_start, locale, t('notAvailable'));

  const periodEnd = formatDate(subscription.current_period_end, locale, t('notAvailable'));

  const renewalLabel = subscription.cancel_at_period_end ? tSubscription('expiresAt') : tSubscription('renewsAt');

  const renewalDate = formatDate(subscription.current_period_end, locale, t('notAvailable'));

  const handleOpenPortal = async () => {
    const toastId = toast.loading(tSubscription('openingPortal'));
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch('/api/portal', {
        method: 'GET',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (response.status === 409) {
        toast.error(tSubscription('portalNoCustomer'));
        return;
      }

      if (!response.ok) {
        toast.error(tSubscription('portalFailed'));
        return;
      }

      const { url } = (await response.json()) as { url?: string };
      if (!url) {
        toast.error(tSubscription('portalInvalidResponse'));
        return;
      }

      window.location.href = url;
    } catch {
      toast.error(tSubscription('portalFailed'));
    } finally {
      toast.dismiss(toastId);
    }
  };

  if (!isInitialized) {
    return <div className="min-h-[60vh] w-full rounded-3xl border border-border/60 bg-muted/20 animate-pulse" />;
  }

  if (isLocal) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="max-w-lg w-full rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl px-8 py-12 text-center space-y-3">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
            <IconCreditCard className="w-5 h-5" />
          </div>
          <h1 className="text-2xl font-semibold text-foreground">{t('notSandboxTitle')}</h1>
          <p className="text-sm text-muted-foreground">{t('notSandboxDesc')}</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <LoginPrompt title={t('loginTitle')} description={t('loginDesc')} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="relative pb-12 space-y-10">
        {ambientBackground}
        {headerSection}
        <section className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl px-6 py-10 text-center space-y-4">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-500/10 text-rose-500 animate-pulse">
            <IconAlertTriangle className="w-5 h-5" />
          </div>
          <h2 className="text-xl font-semibold text-foreground">{t('errorTitle')}</h2>
          <p className="text-sm text-muted-foreground">{t('errorDesc')}</p>
          <button
            onClick={() => refresh()}
            className="inline-flex items-center justify-center rounded-2xl px-5 py-2.5 text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-all"
          >
            {t('retry')}
          </button>
        </section>
      </div>
    );
  }

  if (isEmptyState) {
    return (
      <div className="relative pb-12 space-y-10">
        {ambientBackground}
        {headerSection}
        <section className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl px-6 py-10 text-center space-y-4">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary animate-pulse">
            <IconGlow className="w-5 h-5" />
          </div>
          <h2 className="text-xl font-semibold text-foreground">{t('emptyTitle')}</h2>
          <p className="text-sm text-muted-foreground">{t('emptyDesc')}</p>
          <p className="text-sm text-muted-foreground">{t('toolGatewayNote')}</p>
          <button
            onClick={() => router.push('/pricing')}
            className="inline-flex items-center justify-center rounded-2xl px-5 py-2.5 text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-all"
          >
            {tSubscription('upgradeToPro')}
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="relative pb-12 space-y-10">
      {ambientBackground}

      {headerSection}

      <section className="rounded-2xl border border-border/60 bg-background/70 backdrop-blur-xl px-5 py-4 text-sm text-muted-foreground">
        {t('toolGatewayNote')}
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl p-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
              {tSubscription('currentPlan')}
            </span>
            <IconCrown className="w-4 h-4 text-primary" />
          </div>
          <div className="mt-4 text-2xl font-semibold text-foreground">{planName}</div>
          <p className="mt-2 text-sm text-muted-foreground">{planDescription}</p>
        </div>

        <div className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl p-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
              {tSubscription('status')}
            </span>
            <div
              className={cn(
                'flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold',
                statusMeta.badge,
                statusMeta.tone,
              )}
            >
              <StatusIcon className="w-3 h-3" />
              {tSubscription(statusKey)}
            </div>
          </div>
          <p className="mt-6 text-sm text-muted-foreground">{isHealthy ? t('statusOk') : t('statusAttention')}</p>
        </div>

        <div className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl p-6">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
              {tSubscription('billingCycle')}
            </span>
            <IconCalendar className="w-4 h-4 text-primary" />
          </div>
          <div className="mt-4 text-2xl font-semibold text-foreground">
            {isLoading ? t('loading') : tSubscription(subscription.billing_cycle)}
          </div>
          <p className="mt-2 text-sm text-muted-foreground">
            {renewalLabel}: {renewalDate}
          </p>
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-[2fr_1fr]">
        <div className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl p-6 space-y-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-foreground">{t('periodTitle')}</h2>
            <IconClock className="w-4.5 h-4.5 text-muted-foreground" />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-2xl border border-border/60 bg-muted/20 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">
                {t('periodStart')}
              </p>
              <p className="mt-3 text-lg font-semibold text-foreground">{periodStart}</p>
            </div>
            <div className="rounded-2xl border border-border/60 bg-muted/20 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.3em] text-muted-foreground">{t('periodEnd')}</p>
              <p className="mt-3 text-lg font-semibold text-foreground">{periodEnd}</p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span className="font-semibold text-foreground">{renewalLabel}</span>
            <span>{renewalDate}</span>
            {subscription.cancel_at_period_end && (
              <span className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-500">
                <IconAlertTriangle className="w-3 h-3" />
                {tSubscription('cancelAtPeriodEnd')}
              </span>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl p-6 space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">{t('portalTitle')}</h2>
              <IconCreditCard className="w-4.5 h-4.5 text-muted-foreground" />
            </div>
            <p className="text-sm text-muted-foreground">
              {isPaidPlan ? t('portalDescription') : tSubscription('freeDescription')}
            </p>

            {isPaidPlan ? (
              <button
                onClick={handleOpenPortal}
                disabled={!canOpenPortal}
                className={cn(
                  'w-full inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold transition-all',
                  canOpenPortal
                    ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                    : 'bg-muted text-muted-foreground cursor-not-allowed',
                )}
              >
                {tSubscription('openPortal')}
              </button>
            ) : (
              <button
                onClick={() => router.push('/pricing')}
                className="w-full inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-3 text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-all"
              >
                {tSubscription('upgradeToPro')}
              </button>
            )}

            {!canOpenPortal && isPaidPlan && <p className="text-xs text-muted-foreground">{t('portalUnavailable')}</p>}
          </div>

          {sandbox && isPaidPlan && catalog?.topup_available && (
            <div className="rounded-3xl border border-border/60 bg-background/70 backdrop-blur-xl p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground">{tBilling('topupTitle')}</h2>
              <p className="text-sm text-muted-foreground">
                {tBilling('topupDescription', { rate: String(topupWuPerUsd) })}
              </p>
              <div className="grid grid-cols-3 gap-2">
                {[5, 10, 20].map((amt) => (
                  <button
                    key={amt}
                    disabled={topupLoading}
                    onClick={() => handleTopup(amt)}
                    className="rounded-2xl border border-border/60 bg-muted/20 px-3 py-2.5 text-sm font-semibold text-foreground hover:bg-primary/10 hover:border-primary/30 transition-all disabled:opacity-50"
                  >
                    <div>${amt}</div>
                    <div className="text-xs text-muted-foreground">{(amt * topupWuPerUsd).toLocaleString()} WU</div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-dashed border-border/70 bg-muted/20 px-5 py-4 text-sm text-muted-foreground">
        {t('readonlyNote')}
      </section>
    </div>
  );
}
