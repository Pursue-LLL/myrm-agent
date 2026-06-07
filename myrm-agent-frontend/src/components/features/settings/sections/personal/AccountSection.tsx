'use client';

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import {
  IconActivity,
  IconCalendar,
  IconCheckCircle,
  IconClock,
  IconCreditCard,
  IconCrown,
  IconLock,
  IconLogOut,
  IconMail,
  IconSettings,
  IconShield,
  IconGlow,
  IconUser,
} from '@/components/features/icons/PremiumIcons';
import useAuthStore from '@/store/useAuthStore';
import LoginPrompt from '@/components/features/app-shell/login-prompt';
import { QuotaDisplay } from '@/components/billing/QuotaDisplay';
import { useSubscription } from '@/hooks/useSubscription';
import { isLocalMode } from '@/lib/deploy-mode';
import { cn } from '@/lib/utils/classnameUtils';
import { toast } from '@/lib/utils/toast';

const PlanTierBadge = memo<{ isPro: boolean }>(({ isPro }) => {
  const t = useTranslations('settings.account');
  if (isPro) {
    return (
      <div className="relative group">
        <div className="absolute inset-0 bg-gradient-to-r from-violet-600 to-fuchsia-600 rounded-lg blur opacity-40 group-hover:opacity-60 transition-opacity" />
        <div className="relative flex items-center gap-1.5 px-3 py-1 bg-gradient-to-r from-violet-600 to-fuchsia-600 text-[11px] font-black text-white uppercase tracking-tighter rounded-lg border border-white/20">
          <IconCrown className="w-3.5 h-3.5" />
          {t('badge.pro')}
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1.5 px-3 py-1 bg-white/5 text-muted-foreground text-[11px] font-bold uppercase tracking-tighter rounded-lg border border-white/10">
      <IconGlow className="w-3.5 h-3.5" />
      {t('badge.trial')}
    </div>
  );
});
PlanTierBadge.displayName = 'PlanTierBadge';

const SubscriptionState = memo<{ status: string }>(({ status }) => {
  const t = useTranslations('pricing.subscription');
  const isHealthy = status === 'active';

  return (
    <div
      className={cn(
        'flex items-center gap-1.5 px-2.5 py-1 text-[10px] font-black uppercase tracking-widest rounded-full border',
        isHealthy
          ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20'
          : 'bg-amber-500/10 text-amber-500 border-amber-500/20',
      )}
    >
      <div className={cn('w-1.5 h-1.5 rounded-full animate-pulse', isHealthy ? 'bg-emerald-500' : 'bg-amber-500')} />
      {t(status)}
    </div>
  );
});
SubscriptionState.displayName = 'SubscriptionState';

// ============================================================================
// 主组件
// ============================================================================

const AccountSection = memo(() => {
  const t = useTranslations('settings.account');
  const tQuota = useTranslations('pricing.quota');
  const tSub = useTranslations('pricing.subscription');
  const router = useRouter();
  const { user, logout, isInitialized } = useAuthStore();
  const { subscription, isPro } = useSubscription();
  const [avatarError, setAvatarError] = useState(false);
  const isLocal = isLocalMode();

  const handleLogout = () => logout();

  const handleOpenPortal = async () => {
    const toastId = toast.loading(tSub('openingPortal'));
    try {
      const token = localStorage.getItem('auth_token');
      const response = await fetch('/api/portal', {
        method: 'GET',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });

      if (!response.ok) {
        toast.error(tSub('portalFailed'));
        return;
      }

      const { url } = await response.json();
      if (url) window.location.href = url;
    } catch {
      toast.error(tSub('portalFailed'));
    } finally {
      toast.dismiss(toastId);
    }
  };

  if (!isInitialized) return <div className="h-40 w-full animate-pulse bg-white/5 rounded-3xl" />;
  if (!user)
    return (
      <div className="p-8">
        <LoginPrompt />
      </div>
    );

  const displayName = user?.display_name || user?.email?.split('@')[0] || t('guest');

  return (
    <div className="space-y-12 max-w-4xl mx-auto py-4">
      {/* Profile card section */}
      <section className="relative group">
        <div className="absolute -inset-4 bg-gradient-to-tr from-indigo-500/10 to-transparent rounded-3xl blur-2xl opacity-50 group-hover:opacity-100 transition-opacity" />

        <div className="relative p-8 rounded-[2.5rem] bg-background/40 backdrop-blur-2xl border border-white/10 shadow-2xl flex flex-col md:flex-row items-center gap-8">
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-tr from-indigo-500 to-fuchsia-500 blur-xl opacity-20" />
            {user?.avatar_url && !avatarError ? (
              <Image
                src={user.avatar_url}
                alt={displayName}
                width={120}
                height={120}
                className="relative w-28 h-28 rounded-3xl object-cover ring-4 ring-white/10 shadow-2xl"
                onError={() => setAvatarError(true)}
                unoptimized
              />
            ) : (
              <div className="relative w-28 h-28 rounded-3xl bg-indigo-500/10 flex items-center justify-center ring-4 ring-white/10 text-indigo-500">
                <IconUser className="w-[60px] h-[60px]" />
              </div>
            )}
          </div>

          <div className="flex-1 text-center md:text-left space-y-2">
            <div className="flex flex-col md:flex-row md:items-center gap-3">
              <h1 className="text-3xl font-black tracking-tight text-foreground">{displayName}</h1>
              <div className="flex justify-center md:justify-start">
                <PlanTierBadge isPro={isPro} />
              </div>
            </div>
            <div className="flex flex-wrap justify-center md:justify-start items-center gap-4 text-muted-foreground/60 text-sm font-medium">
              <div className="flex items-center gap-1.5">
                <IconMail className="w-4 h-4" />
                {user.email}
              </div>
              <div className="flex items-center gap-1.5">
                <IconShield className="w-4 h-4 text-emerald-500" />
                {t('verified')}
              </div>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="px-6 py-3 rounded-2xl bg-white/5 hover:bg-rose-500/10 text-muted-foreground hover:text-rose-500 text-sm font-bold transition-all border border-white/5"
          >
            <div className="flex items-center gap-2">
              <IconLogOut className="w-4 h-4" />
              {t('logout')}
            </div>
          </button>
        </div>
      </section>

      {/* Subscription card section */}
      {!isLocal && (
        <section className="space-y-6">
          <div className="flex items-center gap-3 px-2">
            <IconCreditCard className="w-5 h-5 text-muted-foreground" />
            <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
              {t('subscription.title')}
            </h2>
          </div>

          <div
            className={cn(
              'relative overflow-hidden p-1 rounded-[2.5rem]',
              isPro ? 'bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500' : 'bg-white/10',
            )}
          >
            <div className="relative z-10 p-8 rounded-[calc(2.5rem-4px)] bg-background/90 dark:bg-black/80 backdrop-blur-3xl">
              {/* Pattern Overlay */}
              <div
                className="absolute inset-0 opacity-[0.03] pointer-events-none grayscale invert"
                style={{
                  backgroundImage: 'radial-gradient(circle at 2px 2px, white 1px, transparent 0)',
                  backgroundSize: '24px 24px',
                }}
              />

              <div className="flex flex-col md:flex-row gap-12 relative z-10">
                <div className="flex-1 space-y-6">
                  <div className="flex items-start justify-between">
                    <div className="space-y-1">
                      <p className="text-[10px] font-black uppercase tracking-[0.3em] text-muted-foreground/50">
                        {t('subscription.currentStatus')}
                      </p>
                      <h3 className="text-3xl font-black text-foreground">
                        {isPro ? t('subscription.proPlanName') : t('subscription.freePlanName')}
                      </h3>
                    </div>
                    <SubscriptionState status={subscription.status} />
                  </div>

                  <p className="text-muted-foreground/80 leading-relaxed max-w-md">
                    {isPro ? t('subscription.proDescription') : t('subscription.freeDescription')}
                  </p>

                  <div className="flex flex-wrap gap-4">
                    {isPro ? (
                      <button
                        onClick={handleOpenPortal}
                        className="flex items-center gap-2 px-6 py-3 bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl text-sm font-bold transition-all"
                      >
                        <IconSettings className="w-[18px] h-[18px]" /> {t('subscription.billingPortal')}
                      </button>
                    ) : (
                      <button
                        onClick={() => router.push('/pricing')}
                        className="flex items-center gap-2 px-8 py-4 bg-foreground text-background rounded-2xl text-sm font-black uppercase tracking-tighter hover:scale-105 transition-transform shadow-2xl"
                      >
                        <IconCrown className="w-[18px] h-[18px]" /> {t('subscription.upgradeNow')}
                      </button>
                    )}
                  </div>
                </div>

                <div className="w-full md:w-64 space-y-6">
                  <div className="p-6 rounded-3xl bg-white/5 border border-white/5 space-y-4">
                    <div className="space-y-4 text-xs font-bold text-muted-foreground">
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <IconCalendar className="w-3.5 h-3.5" /> {t('subscription.cycle')}
                        </div>
                        <div className="text-foreground">
                          {isPro ? tSub(subscription.billing_cycle) : t('subscription.none')}
                        </div>
                      </div>
                      <div className="flex justify-between items-center">
                        <div className="flex items-center gap-2">
                          <IconClock className="w-3.5 h-3.5" />{' '}
                          {subscription.cancel_at_period_end ? t('subscription.ends') : t('subscription.nextBill')}
                        </div>
                        <div className="text-foreground">
                          {subscription.current_period_end
                            ? new Date(subscription.current_period_end).toLocaleDateString()
                            : t('subscription.none')}
                        </div>
                      </div>
                    </div>
                    {isPro && subscription.cancel_at_period_end && (
                      <div className="pt-2 flex items-center gap-2 text-[10px] text-amber-500/80 font-black uppercase">
                        <IconShield className="w-3 h-3" /> {t('subscription.endingSoon')}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Quota section */}
      {!isLocal && (
        <section className="space-y-6">
          <div className="flex items-center gap-3 px-2">
            <IconActivity className="w-5 h-5 text-muted-foreground" />
            <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
              {tQuota('title')}
            </h2>
          </div>
          <QuotaDisplay />
        </section>
      )}

      {/* Security section */}
      <section className="space-y-6">
        <div className="flex items-center gap-3 px-2">
          <IconShield className="w-5 h-5 text-muted-foreground" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-muted-foreground/70">
            {t('security.title')}
          </h2>
        </div>
        <div className="p-6 rounded-3xl bg-background/40 backdrop-blur-2xl border border-white/10">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-2xl bg-emerald-500/10">
              <IconLock className="w-5 h-5 text-emerald-500" />
            </div>
            <div className="flex-1">
              <h3 className="text-sm font-bold text-foreground">{t('security.serverEncryption')}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">{t('security.serverEncryptionDescription')}</p>
            </div>
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20">
              <IconCheckCircle className="w-3.5 h-3.5 text-emerald-500" />
              <span className="text-[11px] font-bold text-emerald-500">{t('security.active')}</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
});

AccountSection.displayName = 'AccountSection';

export default AccountSection;
